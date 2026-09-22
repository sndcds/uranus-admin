import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, reactive } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import Suggestion from '../../app/components/LocationSuggestion.vue'
import CandidateMap from '../../app/components/CandidateMap.vue'
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
    RequestState: true,
    AppIcon: true,
    GraphLink: { template: '<a>Beziehungen anzeigen</a>' },
    RecordMarkLink: { template: '<a>Markierungen &amp; Notizen</a>' },
  },
}
beforeEach(() => {
  vi.clearAllMocks()
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
  api.admins.mockResolvedValue({ items: [] })
  api.assignmentForWorkflow.mockResolvedValue(null)
})
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
    const secondMarker = view.get('button[aria-label^="Kandidat 2 auf der Karte"]')
    expect(secondMarker.attributes('aria-pressed')).toBe('false')
    await secondMarker.trigger('click')
    expect(secondMarker.attributes('aria-pressed')).toBe('true')
    expect(view.get('li[aria-current="true"] h3').text()).toBe('Zweiter Standort')
    const firstAction = view.get('button[aria-label="Kandidat 1 auf der Karte zeigen"]')
    await firstAction.trigger('click')
    expect(
      view.get('button[aria-label^="Kandidat 1 auf der Karte:"]').attributes('aria-pressed'),
    ).toBe('true')
  })
  it.each([
    ['ambiguous', 'Mehrere mögliche Standorte wurden gefunden. Bitte die Kandidaten vergleichen.'],
    ['not_found', 'Für diese Adresse wurde kein passender Standort gefunden.'],
    ['insufficient_input', 'Für eine zuverlässige Standortsuche fehlen ausreichende Adressdaten.'],
    ['failed', 'Standortprüfung fehlgeschlagen.'],
    ['pending', 'Prüfung vorgemerkt.'],
    ['checking', 'Prüfung läuft.'],
  ] as const)('renders an intentional %s state', (status, message) => {
    const suggestion = { ...structuredClone(geocodeDetail), status, candidates: [] }
    const view = mount(Suggestion, { props: { suggestion }, global })
    expect(view.text()).toContain(message)
    expect(view.findAll('[aria-label="Standortkandidaten"]')).toHaveLength(0)
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
    expect(view.text()).toContain('Prüfung vorgemerkt.')
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
