<script setup lang="ts">
import { useFilterPreferencesStore } from '~/stores/filter-preferences'
import { usePreferenceQuery } from '~/composables/usePreferenceQuery'
import { dashboardPeriods, resolvePeriod } from '~/utils/periods'
import InlineAlert from '~/components/InlineAlert.vue'
import SectionHeader from '~/components/SectionHeader.vue'
import { filtersSchema, periodSchema } from '#shared/contracts'
import type { Severity, FindingFilters } from '#shared/contracts'
import { periodLabels } from '~/utils/presentation'
import { recordRows } from '~/utils/activity'
import { filterQuery } from '~/utils/filters'
const dashboard = useDashboardStore()
const preferences = useFilterPreferencesStore()
const router = useRouter()
const query = usePreferenceQuery(
  { period: preferences.resolvePeriodForPage('dashboard') },
  (value) => preferences.hydratePeriod('dashboard', value.period ?? '24h'),
)
const period = computed(() => resolvePeriod('dashboard', query.value.period))
function setPeriod(value: unknown) {
  const selected = periodSchema.parse(value)
  preferences.hydratePeriod('dashboard', selected)
  void router.push({ query: { period: selected } })
}
watch(period, () => void dashboard.load($adminApi, period.value))
const findings = useFindingsStore()
const { $adminApi } = useNuxtApp()
const displayedPeriod = computed(() => dashboard.data?.period ?? period.value)
const previewFilters = filtersSchema.parse({ page_size: 4 })
onMounted(() => {
  if (dashboard.data?.period !== period.value) void dashboard.load($adminApi, period.value)
  findings.syncQuery(previewFilters)
  void findings.load($adminApi)
})
function previewSeverity(severity?: Severity) {
  findings.setFilters({ severity, page_size: 4 })
  void findings.load($adminApi)
}
function openFilters(filters: FindingFilters) {
  return navigateTo({ path: '/findings', query: filterQuery(filters) })
}
</script>

<template>
  <div class="space-y-5">
    <PageHeader
      title="Dashboard"
      description="Neue Datensätze im Zeitraum und aktueller Arbeitsbestand."
    >
      <label class="text-sm"
        ><span class="sr-only">Zeitraum</span
        ><select
          :value="period"
          class="input"
          aria-label="Zeitraum"
          @change="setPeriod(($event.target as HTMLSelectElement).value)"
        >
          <option v-for="(label, value) in dashboardPeriods" :key="value" :value="value">
            {{ label }}
          </option>
        </select></label
      >

      <button
        class="button"
        :disabled="dashboard.loading"
        @click="dashboard.load($adminApi, period)"
      >
        <AppIcon name="refresh" :size="16" /> Zahlen aktualisieren
      </button>
    </PageHeader>
    <RequestState
      :loading="dashboard.loading"
      :error="dashboard.error"
      :has-data="!!dashboard.data"
      :last-success="dashboard.lastSuccess"
      @retry="dashboard.load($adminApi, period)"
    />
    <InlineAlert
      v-if="dashboard.data && dashboard.data.period !== period"
      tone="warning"
      role="status"
    >
      Die sichtbaren Zahlen gehören noch zum vorherigen Zeitraum. Die Links öffnen den neu gewählten
      Zeitraum.
    </InlineAlert>
    <section
      id="new-records"
      class="scroll-mt-28 space-y-3"
      :aria-busy="dashboard.loading"
      aria-labelledby="new-records-title"
    >
      <div class="space-y-1">
        <SectionHeader title-id="new-records-title" title="Neu eingegangen" />
        <p class="text-sm text-slate-600">
          <strong class="font-semibold tabular-nums text-slate-900">{{
            metric(dashboard.data?.new_records.total)
          }}</strong>
          neue Datensätze · {{ periodLabels[displayedPeriod] }}
        </p>
        <p v-if="dashboard.data" class="mt-1 text-xs text-slate-500">
          {{ dateTime(dashboard.data.from_at) }} – {{ dateTime(dashboard.data.to_at) }} ·
          {{ dashboard.data.admin_timezone }}
        </p>
      </div>
      <ul class="grid grid-cols-2 gap-2 md:grid-cols-3">
        <li v-for="row in recordRows(dashboard.data)" :key="row.key" class="min-w-0">
          <NuxtLink
            :to="{
              path: '/activity',
              query: { period: period, entity_type: row.type },
            }"
            :aria-label="`${row.plural}: ${row.value} · ${periodLabels[displayedPeriod]} · Neue Datensätze ansehen`"
            class="group grid h-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 rounded-2xl border border-slate-200 bg-white p-3 transition-colors hover:border-fuchsia-200 hover:bg-fuchsia-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fuchsia-600"
          >
            <span
              class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
              :class="row.tone"
              ><AppIcon :name="row.icon" :size="18"
            /></span>
            <div class="min-w-0">
              <span class="block break-words text-xs text-slate-600 group-hover:text-fuchsia-800">{{
                row.plural
              }}</span
              ><span class="block text-lg font-semibold tabular-nums">{{ row.value }}</span>
            </div>
            <AppIcon
              name="arrow"
              :size="14"
              class="self-center text-slate-400 group-hover:text-fuchsia-700"
            />
          </NuxtLink>
        </li>
      </ul>
      <p class="text-xs text-slate-500">
        <NuxtLink
          :to="{ path: '/activity', query: { period: period } }"
          class="font-semibold text-fuchsia-700"
          >Einzelne Neuanlagen anzeigen →</NuxtLink
        >
      </p>
    </section>
    <section id="attention" class="space-y-3" aria-labelledby="attention-title">
      <div>
        <SectionHeader title-id="attention-title" title="Was braucht Aufmerksamkeit?" />
        <p class="mt-1 muted">
          Aktuelle offene Vorgänge und Datenprobleme · unabhängig vom gewählten Zeitraum.
        </p>
      </div>
      <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" :aria-busy="dashboard.loading">
        <KpiCard
          label="Dringend"
          :value="dashboard.data?.urgent_findings"
          description="Aktuell dringende Befunde · gesamte Arbeitsliste öffnen"
          tone="rose"
          :to="`/findings?mode=${dashboard.data?.quality.mode ?? 'persisted'}`"
        />
        <KpiCard
          label="Datenqualität"
          :value="dashboard.data?.quality.total"
          :description="
            dashboard.data
              ? `${metric(dashboard.data.quality.errors)} Fehler · ${metric(dashboard.data.quality.warnings)} Warnungen · ${metric(dashboard.data.quality.info)} Hinweise`
              : 'Aktuell nicht erledigte Befunde'
          "
          tone="fuchsia"
          to="/quality"
        />
        <KpiCard
          label="Offene Vorgänge"
          description="Aktueller Vorgangsbestand · keine Gesamtzahl verfügbar"
          to="/#open-queues"
        />
        <DashboardCheckStatus :status="dashboard.data?.check_status" />
      </div>
      <p class="text-xs text-slate-500">
        {{
          dashboard.data?.quality.mode === 'live'
            ? 'Live-Diagnose'
            : 'Gespeicherter Bestand ohne behobene Befunde; einschließlich Zurückstellungen und Ausnahmen'
        }}. Dringend: Priorität 1/2 oder Bezug zu bald stattfindenden veröffentlichten Terminen.
      </p>
    </section>

    <section class="grid gap-4 xl:grid-cols-[1.55fr_.75fr]">
      <div class="min-w-0 space-y-3">
        <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <SectionHeader title="Priorisierte Arbeitsliste" />
            <p class="mt-1 muted">
              Zuerst Probleme an veröffentlichten oder bald stattfindenden Inhalten.
            </p>
          </div>
          <div class="flex gap-1" aria-label="Arbeitsliste nach Schweregrad">
            <button
              v-for="option in [
                { value: undefined, label: 'Alle' },
                { value: 'error' as const, label: 'Fehler' },
                { value: 'warning' as const, label: 'Warnungen' },
              ]"
              :key="option.label"
              class="rounded-lg px-3 py-2 text-xs font-semibold"
              :class="
                findings.filters.severity === option.value
                  ? 'bg-slate-100 text-slate-800'
                  : 'text-slate-600 hover:bg-slate-50'
              "
              :aria-pressed="findings.filters.severity === option.value"
              @click="previewSeverity(option.value)"
            >
              {{ option.label }}
            </button>
          </div>
        </div>
        <div v-if="findings.error || findings.loading" class="p-5">
          <RequestState
            :loading="findings.loading"
            :error="findings.error"
            :has-data="!!findings.data"
            :last-success="findings.lastSuccess"
            @retry="findings.load($adminApi)"
          />
        </div>
        <DataListShell v-if="findings.data?.items.length"
          ><FindingsList :items="findings.data.items"
        /></DataListShell>
        <EmptyState
          v-else-if="findings.data && !findings.loading"
          message="Keine Befunde für diese Auswahl."
        />
        <div class="text-sm">
          <NuxtLink
            :to="{
              path: '/findings',
              query: findings.filters.severity ? { severity: findings.filters.severity } : {},
            }"
            class="text-sm font-semibold text-fuchsia-700"
            >{{
              findings.data
                ? `Alle ${metric(findings.data.pagination.total)} Befunde anzeigen`
                : 'Zur Arbeitsliste'
            }}
            →</NuxtLink
          >
        </div>
      </div>
      <div class="min-w-0 space-y-4">
        <QualityOverview :data="dashboard.data" :limit="5" />
      </div>
    </section>

    <section id="open-queues" class="scroll-mt-28 space-y-3" aria-labelledby="queues-title">
      <div>
        <SectionHeader title-id="queues-title" title="Offene Vorgänge" />
        <p class="mt-1 muted">Arbeitslisten mit tatsächlichem Zustand und belegtem Alter.</p>
      </div>
      <DataListShell as="ul" class="divide-y divide-slate-100">
        <li
          v-for="queue in [
            { path: 'partner_requests', label: 'Partneranfragen' },
            { path: 'team_invitations', label: 'Teameinladungen' },
            { path: 'user_activation', label: 'Aktivierungen' },
          ]"
          :key="queue.path"
        >
          <NuxtLink
            :to="`/queues/${queue.path}`"
            class="data-row flex items-center justify-between gap-3 text-sm font-semibold text-slate-700 hover:text-fuchsia-700"
          >
            {{ queue.label }}<AppIcon name="arrow" :size="16" class="text-fuchsia-700" />
          </NuxtLink>
        </li>
      </DataListShell>
    </section>
    <section class="space-y-3" aria-labelledby="quick-filters-title">
      <SectionHeader title-id="quick-filters-title" title="Schnellfilter" />
      <FilterForm
        :filters="filtersSchema.parse({})"
        @apply="openFilters"
        @reset="openFilters(filtersSchema.parse({}))"
      />
    </section>
  </div>
</template>
