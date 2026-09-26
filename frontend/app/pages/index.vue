<script setup lang="ts">
import { useFilterPreferencesStore } from '~/stores/filter-preferences'
import { usePreferenceQuery } from '~/composables/usePreferenceQuery'
import { dashboardPeriods, resolvePeriod } from '~/utils/periods'
import InlineAlert from '~/components/InlineAlert.vue'
import SectionHeader from '~/components/SectionHeader.vue'
import { filtersSchema, periodSchema } from '#shared/contracts'
import type { Severity, FindingFilters } from '#shared/contracts'
import { periodLabels, metric, recordDateTime, checkStatusLabels } from '~/utils/presentation'
import type { TechnicalFact } from '~/utils/operations'
import { isSpatialType } from '~/utils/geo'
import { recordRows } from '~/utils/activity'
import { filterQuery } from '~/utils/filters'
const operations = ref<{ refresh: () => Promise<unknown> } | null>(null)
function refreshAll() {
  loadDashboard()
  void operations.value?.refresh()
}
const dashboard = useDashboardStore()
const preferences = useFilterPreferencesStore()
const router = useRouter()
const query = usePreferenceQuery(
  { period: preferences.resolvePeriodForPage('dashboard') },
  (value) => preferences.hydratePeriod('dashboard', value.period ?? '24h'),
)
const geoScopeId = computed(() =>
  typeof query.value.geo_scope_id === 'string' ? query.value.geo_scope_id : undefined,
)
const period = computed(() => resolvePeriod('dashboard', query.value.period))
function setPeriod(value: unknown) {
  const selected = periodSchema.parse(value)
  preferences.hydratePeriod('dashboard', selected)
  void router.push({ query: { period: selected, geo_scope_id: geoScopeId.value } })
}
watch([period, geoScopeId], loadDashboard)
const findings = useFindingsStore()
const { $adminApi } = useNuxtApp()
const displayedPeriod = computed(() => dashboard.data?.period ?? period.value)
const previewFilters = filtersSchema.parse({ page_size: 4, active_only: true })
const previewSeverityFilter = ref<Severity | undefined>()
function loadDashboard() {
  void dashboard.load($adminApi, period.value, geoScopeId.value)
  findings.syncQuery({
    ...previewFilters,
    severity: previewSeverityFilter.value,
    geo_scope_id: geoScopeId.value,
  })
  void findings.load($adminApi)
}
onMounted(loadDashboard)
function recordLink(type: string) {
  if (geoScopeId.value && !isSpatialType(type)) {
    const globalPaths: Record<string, string> = {
      user: '/users',
      image: '/images',
      partner_request: '/queues/partner_requests',
      team_membership: '/queues/team_invitations',
    }
    return { path: globalPaths[type] ?? '/activity' }
  }
  return {
    path: '/activity',
    query: { period: period.value, entity_type: type, geo_scope_id: geoScopeId.value },
  }
}
function previewSeverity(severity?: Severity) {
  previewSeverityFilter.value = severity
  findings.setFilters({ severity, page_size: 4, active_only: true })
  void findings.load($adminApi)
}
function openFilters(filters: FindingFilters) {
  return navigateTo({
    path: '/findings',
    query: { ...filterQuery({ ...filters, active_only: true }), geo_scope_id: geoScopeId.value },
  })
}
const technicalItems = computed<TechnicalFact[]>(() => {
  const data = dashboard.data
  if (!data) return []
  const latest = data.check_status?.latest_run
  const successful = data.check_status?.last_successful_run
  const formatTime = (value: string) => recordDateTime(value, data.admin_timezone)
  return [
    {
      label: 'Letzter erfolgreicher Abruf',
      value: dashboard.lastSuccess ? formatTime(dashboard.lastSuccess) : null,
      metadata: 'Client-Abrufzeit',
    },
    { label: 'Zeitraum', value: `${formatTime(data.from_at)} – ${formatTime(data.to_at)}` },
    { label: 'Admin-Zeitzone', value: data.admin_timezone },
    {
      label: 'Qualitätsmodus',
      value:
        data.quality.mode === 'live'
          ? 'Live-Diagnose'
          : data.quality.mode === 'persisted'
            ? 'Gespeicherte Befunde'
            : null,
    },
    {
      label: 'Letzter Prüflauf',
      value: latest
        ? `${checkStatusLabels[latest.status]} · ${formatTime(latest.started_at)}`
        : null,
      metadata: latest ? 'Startzeit · Systemweit' : undefined,
    },
    {
      label: 'Letzter erfolgreicher Prüflauf',
      value: successful?.finished_at ? formatTime(successful.finished_at) : null,
      metadata: successful?.finished_at ? 'Abschluss · Systemweit' : undefined,
    },
    {
      label: 'Geo Scope',
      value: data.geo_scope_id
        ? preferences.sharedGeoScope?.id === data.geo_scope_id
          ? preferences.sharedGeoScope.name
          : data.geo_scope_id
        : null,
    },
  ]
})
</script>

<template>
  <div class="operations-page">
    <PageHeader
      title="Dashboard"
      description="Neue Datensätze im Zeitraum und aktueller Arbeitsbestand."
    >
      <label class="min-w-0 flex-1 text-sm sm:flex-initial"
        ><span class="sr-only">Zeitraum</span>
        <select
          :value="period"
          class="input"
          aria-label="Zeitraum"
          @change="setPeriod(($event.target as HTMLSelectElement).value)"
        >
          <option v-for="(label, value) in dashboardPeriods" :key="value" :value="value">
            {{ label }}
          </option>
        </select>
      </label>
      <button
        class="button-primary shrink-0"
        aria-label="Zahlen aktualisieren"
        :disabled="dashboard.loading"
        @click="refreshAll"
      >
        <AppIcon name="refresh" :size="16" /><span class="hidden min-[375px]:inline"
          >Aktualisieren</span
        >
      </button>
    </PageHeader>
    <RequestState
      :loading="dashboard.loading"
      :error="dashboard.error"
      :has-data="!!dashboard.data"
      :last-success="dashboard.lastSuccess"
      @retry="dashboard.load($adminApi, period, geoScopeId)"
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
      class="space-y-2 scroll-mt-32 lg:scroll-mt-20"
      aria-labelledby="new-records-title"
      :aria-busy="dashboard.loading"
    >
      <SectionHeader title-id="new-records-title" title="Neu eingegangen">
        <NuxtLink :to="{ path: '/activity', query: { period: period } }" class="action-link text-xs"
          >Einzelne Neuanlagen anzeigen →</NuxtLink
        >
      </SectionHeader>
      <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p class="text-xs text-slate-600">
          <strong class="font-semibold tabular-nums text-slate-900">{{
            metric(
              geoScopeId
                ? dashboard.data?.scoped_new_records_total
                : dashboard.data?.new_records.total,
            )
          }}</strong>
          neue Datensätze <template v-if="geoScopeId">im Gebiet</template> ·
          {{ periodLabels[displayedPeriod] }}
          <span v-if="geoScopeId" class="block"
            >Systemweit zusätzlich: {{ metric(dashboard.data?.global_new_records_total) }} nicht
            räumlich zuordenbare Neuanlagen.</span
          >
        </p>
        <p v-if="dashboard.data" class="operations-meta">
          {{ recordDateTime(dashboard.data.from_at, dashboard.data.admin_timezone) }} –
          {{ recordDateTime(dashboard.data.to_at, dashboard.data.admin_timezone) }} ·
          {{ dashboard.data.admin_timezone }}
        </p>
      </div>
      <ul class="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-5">
        <li v-for="row in recordRows(dashboard.data)" :key="row.key" class="min-w-0">
          <NuxtLink
            :to="recordLink(row.type)"
            :aria-label="`${row.plural}: ${row.value} · ${periodLabels[displayedPeriod]} · Neue Datensätze ansehen`"
            class="operations-panel group grid min-h-14 grid-cols-[minmax(0,1fr)] min-[460px]:grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 px-3 py-1.5 hover:border-fuchsia-300 hover:bg-fuchsia-50"
          >
            <span
              class="hidden min-[460px]:flex h-7 w-7 shrink-0 items-center justify-center rounded-lg"
              :class="row.tone"
              ><AppIcon :name="row.icon" :size="16"
            /></span>
            <div class="min-w-0">
              <span
                data-dashboard-new-record-label
                class="block break-words text-xs text-slate-600 group-hover:text-fuchsia-800"
                >{{ row.plural }}</span
              >
              <div class="flex flex-wrap items-baseline gap-x-2">
                <span class="text-xl font-semibold tabular-nums">{{ row.value }}</span
                ><span v-if="geoScopeId" class="text-xs text-slate-600">{{
                  dashboard.data?.new_record_scopes?.[row.key] === 'geo' ? 'Gebiet' : 'Systemweit'
                }}</span>
              </div>
            </div>
            <AppIcon
              name="arrow"
              :size="14"
              class="hidden min-[460px]:block text-slate-400 group-hover:text-fuchsia-700"
            />
          </NuxtLink>
        </li>
      </ul>
    </section>
    <section id="attention" class="space-y-3" aria-labelledby="attention-title">
      <SectionHeader title-id="attention-title" title="Was braucht Aufmerksamkeit?">
        <template #meta
          ><p class="operations-meta mt-1">
            <template v-if="geoScopeId">Qualitätskennzahlen im ausgewählten Gebiet. </template
            >Aktueller Bestand · unabhängig vom gewählten Zeitraum.<template v-if="geoScopeId">
              Prüfstatus und offene Vorgänge: Systemweit.</template
            >
          </p></template
        >
      </SectionHeader>
      <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" :aria-busy="dashboard.loading">
        <KpiCard
          compact
          label="Dringend"
          :value="dashboard.data?.urgent_findings"
          description="Aktuell dringende Befunde · gesamte Arbeitsliste öffnen"
          tone="rose"
          :to="`/findings?mode=${dashboard.data?.quality.mode ?? 'persisted'}&active_only=true${geoScopeId ? '&geo_scope_id=' + encodeURIComponent(geoScopeId) : ''}`"
        />
        <KpiCard
          compact
          label="Datenqualität"
          :value="dashboard.data?.quality.total"
          :description="
            dashboard.data
              ? `${metric(dashboard.data.quality.errors)} Fehler · ${metric(dashboard.data.quality.warnings)} Warnungen · ${metric(dashboard.data.quality.info)} Hinweise`
              : 'Aktuell nicht erledigte Befunde'
          "
          to="/quality"
        />
        <KpiCard
          compact
          label="Offene Vorgänge"
          value-label="3 Arbeitslisten"
          description="Systemweit · keine Gesamtzahl verfügbar"
          to="/#open-queues"
        />
        <DashboardCheckStatus compact :status="dashboard.data?.check_status" />
      </div>
      <p class="operations-meta">
        {{
          dashboard.data?.quality.mode === 'live'
            ? 'Live-Diagnose'
            : 'Gespeicherter Bestand ohne behobene Befunde; einschließlich Zurückstellungen und Ausnahmen'
        }}. Dringend: Priorität 1/2 oder Bezug zu bald stattfindenden veröffentlichten Terminen.
      </p>
    </section>
    <div class="grid items-start gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(0,.8fr)]">
      <RecordSection
        title="Priorisierte Arbeitsliste"
        surface="table"
        description="Zuerst Probleme an veröffentlichten oder bald stattfindenden Inhalten."
      >
        <template #actions>
          <div
            class="flex flex-wrap gap-1 rounded-lg border border-slate-200 bg-white p-0.5"
            role="group"
            aria-label="Arbeitsliste nach Schweregrad"
          >
            <button
              v-for="option in [
                { value: undefined, label: 'Alle' },
                { value: 'error' as const, label: 'Fehler' },
                { value: 'warning' as const, label: 'Warnungen' },
              ]"
              :key="option.label"
              class="min-h-11 rounded-lg px-3 py-2 text-xs font-semibold"
              :class="
                findings.filters.severity === option.value
                  ? 'bg-fuchsia-50 text-fuchsia-800'
                  : 'text-slate-600 hover:bg-slate-50'
              "
              :aria-pressed="findings.filters.severity === option.value"
              @click="previewSeverity(option.value)"
            >
              {{ option.label }}
            </button>
          </div>
        </template>
        <div v-if="findings.error || findings.loading" class="p-3">
          <RequestState
            :loading="findings.loading"
            :error="findings.error"
            :has-data="!!findings.data"
            :last-success="findings.lastSuccess"
            @retry="findings.load($adminApi)"
          />
        </div>
        <FindingsList
          v-if="findings.data?.items.length"
          compact
          :items="findings.data.items"
          :mode="findings.data.mode ?? findings.filters.mode"
        />
        <EmptyState
          v-else-if="findings.data && !findings.loading"
          compact
          class="m-3"
          message="Keine Befunde für diese Auswahl."
        />
        <div class="border-t border-slate-200 px-3">
          <NuxtLink
            :to="{
              path: '/findings',
              query: {
                active_only: 'true',
                severity: findings.filters.severity,
                geo_scope_id: geoScopeId,
              },
            }"
            class="action-link text-xs"
            >{{
              findings.data
                ? `Alle ${metric(findings.data.pagination.total)} Befunde anzeigen`
                : 'Zur Arbeitsliste'
            }}
            →</NuxtLink
          >
        </div>
      </RecordSection>
      <div class="min-w-0 space-y-3">
        <QualityOverview compact :data="dashboard.data" :limit="5" />
        <RecordSection
          id="open-queues"
          title="Offene Vorgänge"
          surface="table"
          class="scroll-mt-32 lg:scroll-mt-20"
          description="Systemweit · ohne aggregierte Gesamtzahl"
        >
          <ul class="divide-y divide-slate-200">
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
                class="flex min-h-11 items-center justify-between gap-3 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 hover:text-fuchsia-700"
                >{{ queue.label }}<AppIcon name="arrow" :size="16"
              /></NuxtLink>
            </li>
          </ul>
        </RecordSection>
      </div>
    </div>
    <DashboardOperations ref="operations" :period="period" :geo-scope-id="geoScopeId" />
    <details class="operations-panel">
      <summary class="min-h-11 cursor-pointer rounded-xl px-4 py-3 text-sm font-semibold">
        Erweiterte Filter
      </summary>
      <div class="border-t border-slate-200">
        <FilterForm
          :filters="filtersSchema.parse({})"
          @apply="openFilters"
          @reset="openFilters(filtersSchema.parse({}))"
        />
      </div>
    </details>
    <TechnicalInfoBar :items="technicalItems" />
  </div>
</template>
