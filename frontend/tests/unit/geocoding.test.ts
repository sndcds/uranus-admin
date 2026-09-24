import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, reactive } from 'vue'
import { mount, flushPromises, enableAutoUnmount } from '@vue/test-utils'
import RecordSection from '../../app/components/RecordSection.vue'
import GeocodeSourceSummary from '../../app/components/GeocodeSourceSummary.vue'
import GeocodeTechnicalMetadata from '../../app/components/GeocodeTechnicalMetadata.vue'
import RequestState from '../../app/components/RequestState.vue'
import { AdminApiError, failure } from '../../shared/errors'
import Suggestion from '../../app/components/LocationSuggestion.vue'
import CandidateMap from '../../app/components/CandidateMap.vue'
import { createPinia, setActivePinia } from 'pinia'
import AssignmentEditor from '../../app/components/AssignmentEditor.vue'
import Detail from '../../app/pages/geocoding/[id].vue'
import List from '../../app/pages/geocoding/index.vue'
import PageHeader from '../../app/components/PageHeader.vue'
import FilterBar from '../../app/components/FilterBar.vue'
import DataListShell from '../../app/components/DataListShell.vue'
import ResultSummary from '../../app/components/ResultSummary.vue'
import PaginationBar from '../../app/components/PaginationBar.vue'
import DetailFacts from '../../app/components/DetailFacts.vue'
import EmptyState from '../../app/components/EmptyState.vue'
import EntityTypeBadge from '../../app/components/EntityTypeBadge.vue'
import InlineAlert from '../../app/components/InlineAlert.vue'
import OsmAttribution from '../../app/components/OsmAttribution.vue'
import SectionHeader from '../../app/components/SectionHeader.vue'
import StatusBadge from '../../app/components/StatusBadge.vue'
import { geocodeDetail, geocodePage } from '../fixtures/geocoding'
import {
  geocodeCandidateSchema,
  geocodeRequestDetailSchema,
  geocodeStatusSchema,
} from '../../shared/contracts'
import { geocodeMessages } from '../../app/utils/geocoding'
import { supportsGeoScope } from '../../app/utils/geo'
import { createAdminApi } from '../../app/utils/admin-api'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'
const api = {
  geocodeRequests: vi.fn(),
  geocodeRequest: vi.fn(),
  retryGeocodeRequest: vi.fn(),
  admins: vi.fn(),
  assignmentForWorkflow: vi.fn(),
  createAssignment: vi.fn(),
  updateAssignment: vi.fn(),
}
const route = reactive({
  params: { id: geocodeDetail.id },
  query: {} as Record<string, string | undefined>,
})
const NuxtLink = defineComponent({
  props: ['to'],
  setup:
    (props, { slots }) =>
    () =>
      h('a', { href: typeof props.to === 'string' ? props.to : '' }, slots.default?.()),
})
const global = {
  components: {
    RecordSection,
    GeocodeSourceSummary,
    GeocodeTechnicalMetadata,
    RequestState,
    AssignmentEditor,
    CandidateMap,
    DetailFacts,
    EmptyState,
    EntityTypeBadge,
    PageHeader,
    FilterBar,
    DataListShell,
    InlineAlert,
    OsmAttribution,
    ResultSummary,
    PaginationBar,
    LocationSuggestion: Suggestion,
    SectionHeader,
    StatusBadge,
  },
  stubs: {
    NuxtLink,
    CandidateMap: {
      props: ['candidates', 'selectedId'],
      emits: ['select'],
      template: '<div />',
      methods: { focusCandidate() {} },
    },
    AppIcon: true,
    GraphLink: { template: '<a>Beziehungen</a>' },
    RecordMarkLink: { template: '<a>Markierungen &amp; Notizen</a>' },
  },
}
beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  route.query = {}
  route.params.id = geocodeDetail.id
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
  vi.stubGlobal('useRoute', () => route)
  vi.stubGlobal('useRouter', () => ({
    push: async ({ query }: { query: Record<string, string | undefined> }) => {
      route.query = query
    },
  }))
  api.geocodeRequests.mockResolvedValue(structuredClone(geocodePage))
  api.geocodeRequest.mockResolvedValue(structuredClone(geocodeDetail))
  api.admins.mockResolvedValue({ items: [], admin_timezone: 'Europe/Berlin' })
  api.assignmentForWorkflow.mockResolvedValue(null)
})
enableAutoUnmount(afterEach)
afterEach(() => vi.unstubAllGlobals())
describe('location suggestions', () => {
  it.each(geocodeStatusSchema.options)('renders safe status %s', (status) => {
    const view = mount(Suggestion, { props: { suggestion: { ...geocodeDetail, status } }, global })
    expect(view.text()).toContain(geocodeMessages[status])
    expect(
      view.findAll('button').some((button) => /übernehmen|akzeptieren/i.test(button.text())),
    ).toBe(false)
  })
  it('escapes provider text, shows address score, reasons and multiple candidates', () => {
    const suggestion = structuredClone(geocodeDetail)
    suggestion.status = 'ambiguous'
    suggestion.candidates.push({
      ...suggestion.candidates[0]!,
      id: '00000000-0000-4000-8000-000000000903',
      display_name: '<script>alert(1)</script>',
    })
    const view = mount(Suggestion, { props: { suggestion }, global })
    expect(view.findAll('script')).toHaveLength(0)
    expect(view.text()).toContain('<script>alert(1)</script>')
    expect(view.text()).toContain('100 % Adressübereinstimmung')
    expect(view.text()).toContain('Hausnummer stimmt überein')
    expect(view.text()).toContain('Bester automatischer Treffer')
    expect(view.findAll('a[href="https://www.openstreetmap.org/way/123"]')).toHaveLength(2)
  })
  it('synchronizes keyboard-accessible map markers and candidate rows', async () => {
    const suggestion = structuredClone(geocodeDetail)
    suggestion.status = 'ambiguous'
    suggestion.candidates.push({
      ...suggestion.candidates[0]!,
      id: '00000000-0000-4000-8000-000000000903',
      rank: 2,
      latitude: 54.7,
      longitude: 9.8,
      display_name: 'Zweiter Standort',
    })
    const view = mount(Suggestion, { props: { suggestion }, global })
    const map = view.findComponent(CandidateMap)
    expect(map.props('candidates')).toHaveLength(2)
    map.vm.$emit('select', suggestion.candidates[1]!.id)
    await flushPromises()
    expect(view.get('li[aria-current="true"] h4').text()).toBe('Zweiter Standort')
    expect(map.props('selectedId')).toBe(suggestion.candidates[1]!.id)
    await view.get('button[aria-label="Kandidat 1 auf der Karte zeigen"]').trigger('click')
    expect(map.props('selectedId')).toBe(suggestion.candidates[0]!.id)
  })
  it.each(geocodeStatusSchema.options)('renders %s without invented candidates', (status) => {
    const view = mount(Suggestion, {
      props: { suggestion: { ...geocodeDetail, status, candidates: [] } },
      global,
    })
    expect(view.text()).toContain(geocodeMessages[status])
    expect(view.findAll('[aria-label="Standortkandidaten"]')).toHaveLength(0)
  })
  it('selects the stored best candidate even when it is not first and repairs removed selection', async () => {
    const suggestion = structuredClone(geocodeDetail)
    suggestion.candidates.push({
      ...suggestion.candidates[0]!,
      id: '00000000-0000-4000-8000-000000000903',
      rank: 2,
    })
    suggestion.best_candidate = suggestion.candidates[1]!
    const view = mount(Suggestion, { props: { suggestion }, global })
    expect(view.getComponent(CandidateMap).props('selectedId')).toBe(suggestion.candidates[1]!.id)
    await view.setProps({
      suggestion: { ...suggestion, best_candidate: null, candidates: [suggestion.candidates[0]!] },
    })
    expect(view.getComponent(CandidateMap).props('selectedId')).toBe(suggestion.candidates[0]!.id)
    expect(view.get('li[aria-current="true"]').text()).toContain('Ausgewählt')
  })
  it('queues retry once, removes old candidates and shows confirmation', async () => {
    let resolve: () => void = () => {}
    api.retryGeocodeRequest.mockReturnValue(
      new Promise<void>((r) => {
        resolve = r
      }),
    )
    const view = mount(Detail, { global })
    await flushPromises()
    const button = view.findAll('button').find((b) => b.text() === 'Standort erneut prüfen')!
    await button.trigger('click')
    await button.trigger('click')
    expect(api.retryGeocodeRequest).toHaveBeenCalledTimes(1)
    expect(button.attributes('disabled')).toBeDefined()
    resolve()
    await flushPromises()
    expect(view.text()).toContain('Neue Prüfung wurde eingeplant.')
    expect(view.text()).toContain('Prüfung vorgemerkt')
    expect(view.text()).not.toContain('Adressübereinstimmung')
    view.unmount()
  })
  it('shows canonical entity actions and one distinct assignment-unavailable state', async () => {
    const view = mount(Detail, { global })
    await flushPromises()
    expect(view.get(`a[href="/venues/${geocodeDetail.entity_key}"]`).text()).toContain('Ort öffnen')
    expect(view.text()).toContain('Derzeit ist kein aktiver Systemadministrator')
    expect(view.text()).not.toContain('Zuständigkeit konnte nicht geladen werden')
    view.unmount()

    api.assignmentForWorkflow.mockRejectedValueOnce(new Error('unavailable'))
    const failed = mount(Detail, { global })
    await flushPromises()
    expect(failed.text()).toContain('Zuständigkeit konnte nicht geladen werden')
    expect(failed.text()).not.toContain('Derzeit ist kein aktiver Systemadministrator')
    failed.unmount()
  })
  it('has one page title, a compact source, a single comparison and technical metadata last', async () => {
    const view = mount(Detail, { global })
    await flushPromises()
    expect(view.findAll('h2')).toHaveLength(1)
    const source = view.get('[data-geocode-source]')
    expect(source.text()).toContain(geocodeDetail.entity_name)
    expect(source.text()).toContain(geocodeDetail.source_address)
    expect(source.text()).not.toMatch(/Generation|Prüfversuche/)
    expect(view.text().match(/Standortvorschlag vorhanden/g)).toHaveLength(1)
    expect(view.get('[data-candidate-comparison]').findAll('h4')).toHaveLength(1)
    expect(view.find('button[aria-label="Kandidat 1 auf der Karte zeigen"]').exists()).toBe(false)
    expect(view.get('li[aria-current="true"]').text()).toContain('Ausgewählt')
    const retry = view
      .findAll('button')
      .find((button) => button.text() === 'Standort erneut prüfen')!
    expect(retry.classes()).not.toContain('button-primary')
    const headings = view.findAll('h3').map((heading) => heading.text())
    expect(headings).toEqual([
      geocodeDetail.entity_name,
      'Standortprüfung',
      'Bearbeitung',
      'Weitere Aktionen',
      'Technische Informationen',
    ])
    const technical = view.findAllComponents(RecordSection).at(-1)!
    expect(technical.text()).toContain('Generation1')
    expect(technical.text()).toContain('Prüfversuche1')
    expect(technical.text()).toContain(geocodeDetail.id)
  })
  it('renders missing source address and unknown check time without inventing values', () => {
    const suggestion = { ...geocodeDetail, source_address: '', checked_at: null }
    const source = mount(GeocodeSourceSummary, { props: { suggestion }, global })
    expect(source.text()).toContain('Keine Adresse vorhanden')
    const technical = mount(GeocodeTechnicalMetadata, { props: { suggestion }, global })
    expect(technical.text()).toContain('Noch nicht geprüft')
    expect(technical.find('time').exists()).toBe(false)
  })
  it('keeps assignment failure compact inside Bearbeitung and retries without disturbing candidates', async () => {
    api.assignmentForWorkflow.mockRejectedValueOnce(new Error('unavailable'))
    const view = mount(Detail, { global })
    await flushPromises()
    const editor = view.getComponent(AssignmentEditor)
    expect(editor.props('embedded')).toBe(true)
    expect(editor.find('h2').exists()).toBe(false)
    expect(editor.getComponent(InlineAlert).props('compact')).toBe(true)
    expect(view.get('[data-candidate-comparison]').exists()).toBe(true)
    await editor.get('button').trigger('click')
    await flushPromises()
    expect(editor.text()).not.toContain('konnte nicht geladen')
    expect(view.get('[data-candidate-comparison]').exists()).toBe(true)
  })
  it('preserves the standalone assignment error without adding a competing workflow retry', async () => {
    api.assignmentForWorkflow.mockRejectedValueOnce(new Error('unavailable'))
    const view = mount(AssignmentEditor, {
      props: {
        workflowType: 'geocode_request',
        workflowKey: geocodeDetail.id,
        entityType: 'venue',
        entityKey: geocodeDetail.entity_key,
      },
      global,
    })
    await flushPromises()
    expect(view.get('h2').text()).toBe('Zuständigkeit')
    expect(view.getComponent(InlineAlert).props('compact')).toBe(false)
    expect(view.find('button').exists()).toBe(false)
  })
  it('preserves the last successful request on refresh and announces stale failures', async () => {
    const view = mount(Detail, { global })
    await flushPromises()
    let reject!: (reason: unknown) => void
    api.geocodeRequest.mockReturnValueOnce(
      new Promise((_resolve, r) => {
        reject = r
      }),
    )
    await view
      .findAll('button')
      .find((button) => button.text().includes('Prüfstand aktualisieren'))!
      .trigger('click')
    expect(view.get('[data-geocode-source]').text()).toContain(geocodeDetail.entity_name)
    expect(view.text()).toContain('Daten werden aktualisiert')
    reject(new Error('network'))
    await flushPromises()
    expect(view.text()).toContain('Die angezeigten Daten sind veraltet.')
    expect(view.get('[data-candidate-comparison]').exists()).toBe(true)
    expect(view.text()).not.toContain('Letzter erfolgreicher Abruf:')
  })
  it.each([401, 403, 404])('clears protected data after refresh status %s', async (status) => {
    const view = mount(Detail, { global })
    await flushPromises()
    api.geocodeRequest.mockRejectedValueOnce(new AdminApiError(failure(status)))
    await view
      .findAll('button')
      .find((button) => button.text().includes('Prüfstand aktualisieren'))!
      .trigger('click')
    await flushPromises()
    expect(view.find('[data-geocode-source]').exists()).toBe(false)
    expect(view.find('[data-candidate-comparison]').exists()).toBe(false)
  })
  it('clears immediately on identity change and ignores an older response', async () => {
    const view = mount(Detail, { global })
    await flushPromises()
    let resolve!: (value: typeof geocodeDetail) => void
    api.geocodeRequest.mockReturnValueOnce(
      new Promise((r) => {
        resolve = r
      }),
    )
    await view
      .findAll('button')
      .find((button) => button.text().includes('Prüfstand aktualisieren'))!
      .trigger('click')
    let next!: (value: typeof geocodeDetail) => void
    api.geocodeRequest.mockReturnValueOnce(
      new Promise((r) => {
        next = r
      }),
    )
    route.params.id = '00000000-0000-4000-8000-000000000999'
    await flushPromises()
    expect(view.find('[data-geocode-source]').exists()).toBe(false)
    next({ ...geocodeDetail, id: route.params.id, entity_name: 'Neuer Datensatz' })
    await flushPromises()
    resolve(geocodeDetail)
    await flushPromises()
    expect(view.get('[data-geocode-source]').text()).toContain('Neuer Datensatz')
    expect(view.text()).not.toContain(geocodeDetail.entity_name)
  })
  it.each([401, 403, 404])('also clears protected data after enqueue status %s', async (status) => {
    const view = mount(Detail, { global })
    await flushPromises()
    api.retryGeocodeRequest.mockRejectedValueOnce(new AdminApiError(failure(status)))
    await view
      .findAll('button')
      .find((button) => button.text() === 'Standort erneut prüfen')!
      .trigger('click')
    await flushPromises()
    expect(view.find('[data-geocode-source]').exists()).toBe(false)
  })
  it('ignores an enqueue response after switching identity', async () => {
    let resolve!: () => void
    api.retryGeocodeRequest.mockReturnValueOnce(
      new Promise<void>((r) => {
        resolve = r
      }),
    )
    const view = mount(Detail, { global })
    await flushPromises()
    await view
      .findAll('button')
      .find((button) => button.text() === 'Standort erneut prüfen')!
      .trigger('click')
    const nextId = '00000000-0000-4000-8000-000000000999'
    api.geocodeRequest.mockResolvedValueOnce({
      ...geocodeDetail,
      id: nextId,
      entity_name: 'Andere Prüfung',
    })
    route.params.id = nextId
    await flushPromises()
    resolve()
    await flushPromises()
    expect(view.text()).toContain('Andere Prüfung')
    expect(view.text()).not.toContain('Neue Prüfung wurde eingeplant.')
    expect(view.get('[data-candidate-comparison]').exists()).toBe(true)
  })
  it('filters and paginates globally without scope', async () => {
    const view = mount(List, { global })
    await flushPromises()
    expect(view.text()).toContain('Diese Ansicht ist systemweit')
    expect(supportsGeoScope('/geocoding')).toBe(false)
    await view.findAll('select')[0]!.setValue('ambiguous')
    await view.findAll('select')[1]!.setValue('organization')
    await view.find('form').trigger('submit')
    await flushPromises()
    expect(api.geocodeRequests).toHaveBeenLastCalledWith({
      status: 'ambiguous',
      entity_type: 'organization',
      page: 1,
      page_size: 50,
    })
    route.query = { ...route.query, page: '2' }
    await flushPromises()
    expect(api.geocodeRequests.mock.lastCall?.[0].page).toBe(2)
    expect(JSON.stringify(api.geocodeRequests.mock.calls)).not.toContain('geo_scope_id')
    view.unmount()
  })
  it('rejects malformed coordinates, states and OSM URLs', () => {
    expect(geocodeRequestDetailSchema.safeParse(geocodeDetail).success).toBe(true)
    for (const changes of [
      { latitude: NaN },
      { longitude: Infinity },
      { latitude: 91 },
      { match_score: 2 },
      { osm_url: 'javascript:alert(1)' },
      { osm_url: 'https://evil.test/way/1' },
      { address: { secret: 'raw' } },
    ])
      expect(
        geocodeCandidateSchema.safeParse({ ...geocodeDetail.candidates[0], ...changes }).success,
      ).toBe(false)
    expect(geocodeStatusSchema.safeParse('accepted').success).toBe(false)
  })
  it('validates client responses and sends a bodyless retry', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ id: geocodeDetail.id, status: 'pending' }), { status: 202 }),
      )
    await createAdminApi(fetcher).retryGeocodeRequest(geocodeDetail.id)
    expect(fetcher.mock.calls[0]?.[1]).toMatchObject({
      method: 'POST',
      headers: expect.objectContaining({ 'X-Admin-CSRF': '1' }),
    })
    expect(fetcher.mock.calls[0]?.[1].body).toBeUndefined()
  })
  it('proxy allows only bounded resource paths and rejects overrides', async () => {
    const base = 'http://127.0.0.1:8000'
    const input = {
      path: `/api/v1/geocode/requests/${geocodeDetail.id}/retry`,
      method: 'POST',
      query: new URLSearchParams(),
      authorization: 'Bearer test',
      origin: 'https://admin.example.test',
      csrf: '1',
    }
    const fetcher = vi.fn().mockResolvedValue(new Response('{}', { status: 202 }))
    expect((await forwardAdminRequest(input, base, fetcher)).status).toBe(202)
    expect(fetcher.mock.calls[0]?.[1].body).toBeUndefined()
    for (const body of [{}, null, { lat: 1 }, { address: 'override' }])
      expect((await forwardAdminRequest({ ...input, body }, base, fetcher)).status).toBe(422)
    for (const query of ['provider=x', 'geo_scope_id=x', 'page=1&page=2'])
      expect(
        (await forwardAdminRequest({ ...input, query: new URLSearchParams(query) }, base, fetcher))
          .status,
      ).toBe(422)
    expect((await forwardAdminRequest({ ...input, method: 'GET' }, base, fetcher)).status).toBe(405)
    expect(
      (
        await forwardAdminRequest(
          { ...input, path: input.path.replace('/retry', '/accept') },
          base,
          fetcher,
        )
      ).status,
    ).toBe(404)
  })
})
