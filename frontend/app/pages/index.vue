<script setup lang="ts">
import { filtersSchema } from '#shared/contracts'
import type { Severity, FindingFilters } from '#shared/contracts'
import { periodLabels } from '~/utils/presentation'
import { recordRows } from '~/utils/activity'
import { filterQuery } from '~/utils/filters'
const dashboard = useDashboardStore()
const findings = useFindingsStore()
const { $adminApi } = useNuxtApp()
const displayedPeriod = computed(() => dashboard.data?.period ?? dashboard.period)
const previewFilters = filtersSchema.parse({ page_size: 4 })
onMounted(() => {
  if (!dashboard.data) void dashboard.load($adminApi)
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
      <button class="button" :disabled="dashboard.loading" @click="dashboard.load($adminApi)">
        <AppIcon name="refresh" :size="16" /> Zahlen aktualisieren
      </button>
    </PageHeader>
    <RequestState
      :loading="dashboard.loading"
      :error="dashboard.error"
      :has-data="!!dashboard.data"
      :last-success="dashboard.lastSuccess"
      @retry="dashboard.load($adminApi)"
    />
    <p
      v-if="dashboard.data && dashboard.data.period !== dashboard.period"
      class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800"
      role="status"
    >
      Die sichtbaren Zahlen gehören noch zum vorherigen Zeitraum. Die Links öffnen den neu gewählten
      Zeitraum.
    </p>
    <section
      id="new-records"
      class="scroll-mt-28 space-y-3"
      :aria-busy="dashboard.loading"
      aria-labelledby="new-records-title"
    >
      <div class="space-y-1">
        <h2 id="new-records-title" class="text-lg font-semibold">Neu eingegangen</h2>
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
              query: { period: dashboard.period, entity_type: row.type },
            }"
            :aria-label="`${row.plural}: ${row.value} · ${periodLabels[displayedPeriod]} · Neue Datensätze ansehen`"
            class="group grid h-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 rounded-xl border border-slate-200 bg-white p-3 transition-colors hover:border-fuchsia-200 hover:bg-fuchsia-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fuchsia-600"
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
          :to="{ path: '/activity', query: { period: dashboard.period } }"
          class="font-semibold text-fuchsia-700"
          >Einzelne Neuanlagen anzeigen →</NuxtLink
        >
      </p>
    </section>
    <section id="attention" class="space-y-3" aria-labelledby="attention-title">
      <div>
        <h2 id="attention-title" class="text-lg font-semibold">Was braucht Aufmerksamkeit?</h2>
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
        <KpiCard
          label="Prüfstatus"
          description="Status nur in den gespeicherten Prüfläufen verfügbar"
          to="/checks"
        />
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
            <h2 class="font-bold">Priorisierte Arbeitsliste</h2>
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
        <h2 id="queues-title" class="text-base font-semibold">Offene Vorgänge</h2>
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
      <h2 id="quick-filters-title" class="text-base font-semibold">Schnellfilter</h2>
      <FilterForm
        :filters="filtersSchema.parse({})"
        @apply="openFilters"
        @reset="openFilters(filtersSchema.parse({}))"
      />
    </section>
  </div>
</template>
