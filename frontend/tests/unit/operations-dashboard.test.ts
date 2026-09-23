import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import * as vue from 'vue'
import Dashboard from '../../app/pages/index.vue'
import PageHeader from '../../app/components/PageHeader.vue'
import RecordSection from '../../app/components/RecordSection.vue'
import KpiCard from '../../app/components/KpiCard.vue'
import DashboardCheckStatus from '../../app/components/DashboardCheckStatus.vue'
import QualityOverview from '../../app/components/QualityOverview.vue'
import FindingsList from '../../app/components/FindingsList.vue'
import FilterForm from '../../app/components/FilterForm.vue'
import FilterBar from '../../app/components/FilterBar.vue'
import TechnicalInfoBar from '../../app/components/TechnicalInfoBar.vue'
import StatusBadge from '../../app/components/StatusBadge.vue'
import SeverityBadge from '../../app/components/SeverityBadge.vue'
import EntityTypeBadge from '../../app/components/EntityTypeBadge.vue'
import RecordMarkLink from '../../app/components/RecordMarkLink.vue'
import EmptyState from '../../app/components/EmptyState.vue'
import { useDashboardStore } from '../../app/stores/dashboard'
import { useFindingsStore } from '../../app/stores/findings'
import { useFilterPreferencesStore } from '../../app/stores/filter-preferences'
import { filtersSchema } from '../../shared/contracts'
import { operationsSummary, operationsFindings } from '../fixtures/operations-dashboard'
import { geoArea } from '../fixtures/geo'

const route = vue.reactive({ path: '/', query: {} as Record<string, string>, hash: '' })
const api = { summary: vi.fn(), findings: vi.fn() }
const navigate = vi.fn()
const wrappers: { unmount: () => void }[] = []
const global = {
  components: {
    PageHeader,
    RecordSection,
    KpiCard,
    DashboardCheckStatus,
    QualityOverview,
    FindingsList,
    FilterForm,
    FilterBar,
    TechnicalInfoBar,
    StatusBadge,
    SeverityBadge,
    EntityTypeBadge,
    RecordMarkLink,
    EmptyState,
  },
  stubs: {
    SqlEditorModal: true,
    AppIcon: true,
    RequestState: true,
    NuxtLink: { name: 'NuxtLink', props: ['to'], template: '<a><slot /></a>' },
  },
}
beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
  route.query = { period: '24h' }
  api.summary.mockResolvedValue(operationsSummary)
  api.findings.mockResolvedValue(operationsFindings)
  for (const key of [
    'ref',
    'computed',
    'watch',
    'onMounted',
    'onBeforeUnmount',
    'useTemplateRef',
  ] as const)
    vi.stubGlobal(key, vue[key])
  vi.stubGlobal('useRoute', () => route)
  vi.stubGlobal('useRouter', () => ({ push: navigate, replace: navigate }))
  vi.stubGlobal('navigateTo', navigate)
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
  vi.stubGlobal('useDashboardStore', useDashboardStore)
  vi.stubGlobal('useFindingsStore', useFindingsStore)
})
afterEach(() => {
  wrappers.splice(0).forEach((w) => w.unmount())
  vi.unstubAllGlobals()
})
async function render() {
  const wrapper = mount(Dashboard, { global })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
}
it('shows all nine incoming types, real zero, four attention KPIs and three uncounted queues', async () => {
  const view = await render()
  expect(view.findAll('[data-dashboard-new-record-label]').map((el) => el.text())).toEqual([
    'Organisationen',
    'Orte',
    'Räume',
    'Veranstaltungen',
    'Termine',
    'Benutzer',
    'Partneranfragen',
    'Teammitgliedschaften',
    'Bilder',
  ])
  expect(view.get('#new-records li:nth-child(3)').text()).toContain('0')
  expect(view.findAllComponents(KpiCard)).toHaveLength(4)
  expect(view.get('#attention').text()).toContain('3 Arbeitslisten')
  expect(view.get('#attention').text()).toContain('194 Fehler · 602 Warnungen · 133 Hinweise')
  expect(view.findAll('#open-queues li').map((el) => el.text())).toEqual([
    'Partneranfragen',
    'Teameinladungen',
    'Aktivierungen',
  ])
  expect(view.find('table summary').exists()).toBe(false)
  expect(view.get('table').findAll('button')).toHaveLength(1)
  expect(view.get('table').text()).not.toContain('Markierungen & Notizen')
})
it('preserves the four-record preview, active-only severity filter and advanced filter navigation', async () => {
  const view = await render()
  expect(api.findings).toHaveBeenLastCalledWith(
    expect.objectContaining({ page_size: 4, active_only: true }),
  )
  expect(view.findAll('table tbody tr')).toHaveLength(4)
  expect(view.findAll('table th[scope="col"]')).toHaveLength(4)
  await view
    .findAll('button')
    .find((el) => el.text() === 'Warnungen')!
    .trigger('click')
  expect(api.findings).toHaveBeenLastCalledWith(
    expect.objectContaining({ severity: 'warning', page_size: 4, active_only: true }),
  )
  const advanced = view
    .findAll('details')
    .find((el) => el.find('summary').text() === 'Erweiterte Filter')!
  expect(advanced.attributes('open')).toBeUndefined()
  view.getComponent(FilterForm).vm.$emit('apply', filtersSchema.parse({ severity: 'error' }))
  expect(navigate).toHaveBeenCalledWith({
    path: '/findings',
    query: expect.objectContaining({ active_only: 'true', severity: 'error' }),
  })
})
it('shows five rules ordered by known counts and keeps aggregate counts distinct', async () => {
  const view = await render()
  const quality = view.getComponent(QualityOverview)
  expect(quality.text()).toContain('929 Befunde')
  expect(quality.text()).toContain('194 Fehler')
  expect(quality.text()).toContain('602 Warnungen')
  expect(quality.text()).toContain('133 Hinweise')
  const rows = quality.findAll('li')
  expect(rows).toHaveLength(5)
  expect(rows[0]!.text()).toContain('254')
  expect(rows[2]!.text()).toContain('194')
  expect(quality.text()).not.toContain('Postleitzahlen mit Leerzeichen')
})
it('retains spatial versus global link semantics and labels the verified geo scope', async () => {
  useFilterPreferencesStore().setGeoScope(geoArea)
  route.query = { period: '24h', geo_scope_id: geoArea.id }
  api.summary.mockResolvedValue({
    ...operationsSummary,
    geo_scope_id: geoArea.id,
    scoped_new_records_total: 39,
    global_new_records_total: 17,
    new_record_scopes: {
      organizations: 'geo',
      venues: 'geo',
      spaces: 'geo',
      events: 'geo',
      event_dates: 'geo',
      users: 'global',
      images: 'global',
      partner_requests: 'global',
      team_memberships: 'global',
    },
  })
  const view = await render()
  const links = view.get('#new-records ul').findAllComponents({ name: 'NuxtLink' })
  expect(links[0]!.props('to')).toMatchObject({
    path: '/activity',
    query: { geo_scope_id: geoArea.id, entity_type: 'organization', period: '24h' },
  })
  expect(links[5]!.props('to')).toEqual({ path: '/users' })
  expect(view.get('#new-records').text()).toContain('Systemweit zusätzlich: 17')
  expect(view.get('#new-records li:first-child').text()).toContain('Gebiet')
  expect(view.get('#new-records li:nth-child(6)').text()).toContain('Systemweit')
  expect(view.getComponent(TechnicalInfoBar).text()).toContain('Flensburg')
})
it('labels fetch time separately from source time and omits unverified technical values', async () => {
  const view = await render()
  const technical = view.getComponent(TechnicalInfoBar)
  expect(technical.findAll('dt').map((el) => el.text())).toEqual([
    'Letzter erfolgreicher Abruf',
    'Zeitraum',
    'Admin-Zeitzone',
    'Qualitätsmodus',
    'Letzter Prüflauf',
    'Letzter erfolgreicher Prüflauf',
  ])
  expect(technical.text()).toContain('Client-Abrufzeit')
  expect(technical.text()).toContain('Europe/Berlin')
  expect(technical.text()).toContain('Gespeicherte Befunde')
  expect(technical.text()).not.toContain('API-Version')
  expect(technical.text()).not.toContain('Datenbank')
  useDashboardStore().data = {
    ...operationsSummary,
    check_status: null,
    quality: { ...operationsSummary.quality, mode: undefined },
  }
  await vue.nextTick()
  expect(technical.text()).not.toContain('Letzter Prüflauf')
  expect(technical.text()).not.toContain('Qualitätsmodus')
})
it.each([
  ['success', 'Erfolgreich'],
  ['failed', 'Fehlgeschlagen'],
  ['running', 'Läuft'],
  ['queued', 'Wartet'],
] as const)('renders compact check status %s', (status, label) => {
  const run = operationsSummary.check_status!.latest_run!
  const view = mount(DashboardCheckStatus, {
    props: { compact: true, status: { latest_run: { ...run, status }, last_successful_run: run } },
    global,
  })
  wrappers.push(view)
  expect(view.text()).toContain(label)
  expect(view.text()).toContain('47 Regeln · 929 Befunde')
  expect(view.get('time').attributes('datetime')).toBe(run.started_at)
})
it('handles missing checks and empty quality/worklist without replacing zero', async () => {
  api.summary.mockResolvedValue({
    ...operationsSummary,
    check_status: { latest_run: null, last_successful_run: null },
    quality: { ...operationsSummary.quality, total: 0, errors: 0, warnings: 0, info: 0 },
  })
  api.findings.mockResolvedValue({
    ...operationsFindings,
    items: [],
    pagination: { page: 1, page_size: 4, total: 0, pages: 0 },
  })
  const view = await render()
  expect(view.text()).toContain('Noch keine Prüfläufe')
  expect(view.text()).toContain('0 Befunde')
  expect(view.text()).toContain('Keine Befunde für diese Auswahl.')
  expect(view.text()).toContain('Keine aktuellen Qualitätsbefunde.')
  expect(view.findAllComponents(EmptyState).every((el) => el.props('compact'))).toBe(true)
  useDashboardStore().data = { ...operationsSummary, check_status: null }
  await vue.nextTick()
  expect(view.getComponent(DashboardCheckStatus).text()).toContain('Nicht verfügbar')
})
