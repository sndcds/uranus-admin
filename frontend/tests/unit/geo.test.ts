import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import { geoArea, geoSearchItem } from '../fixtures/geo'
import { useFilterPreferencesStore } from '../../app/stores/filter-preferences'
import { createAdminApi } from '../../app/utils/admin-api'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'
import { geoAreaImportSchema } from '../../shared/contracts'
import { AdminApiError, failure } from '../../shared/errors'
import GeoScopeSelector from '../../app/components/GeoScopeSelector.vue'
import { supportsGeoScope } from '../../app/utils/geo'
const api = { geoArea: vi.fn(), searchGeoAreas: vi.fn(), importGeoArea: vi.fn() }
const auth = { isAdmin: true, revision: 0 }
const route = reactive({ path: '/events', query: {} as Record<string, string>, hash: '' })
const push = vi.fn(async ({ query }) => {
  route.query = query
})
const navigate = vi.fn((to) => to)
const wrappers: ReturnType<typeof mount>[] = []
beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  route.path = '/events'
  route.query = {}
  auth.isAdmin = true
  auth.revision = 0
  api.geoArea.mockResolvedValue(geoArea)
  api.searchGeoAreas.mockResolvedValue({ items: [geoSearchItem] })
  api.importGeoArea.mockResolvedValue(geoArea)
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
  vi.stubGlobal('useAuthStore', () => auth)
  vi.stubGlobal('useFilterPreferencesStore', useFilterPreferencesStore)
  vi.stubGlobal('useRoute', () => route)
  vi.stubGlobal('useRouter', () => ({ push }))
  vi.stubGlobal('navigateTo', navigate)
  vi.stubGlobal('defineNuxtRouteMiddleware', (fn: unknown) => fn)
})
afterEach(() => {
  wrappers.splice(0).forEach((w) => w.unmount())
  vi.useRealTimers()
  vi.unstubAllGlobals()
})
it('keeps period and geo independent, preserves geo on local reset and clears both on session reset', () => {
  const store = useFilterPreferencesStore()
  store.setGeoScope(geoArea)
  store.setSharedPeriod('90d')
  store.resetEntity('events')
  expect(store.sharedGeoScope).toEqual(geoArea)
  expect(store.sharedPeriod).toBe('90d')
  store.setGeoScope(null)
  expect(store.sharedPeriod).toBe('90d')
  store.setGeoScope(geoArea)
  store.resetAll()
  expect(store.sharedGeoScope).toBeNull()
  expect(store.sharedPeriod).toBe('24h')
  expect(useFilterPreferencesStore(createPinia()).sharedGeoScope).toBeNull()
})
it('resolves URL > session > no scope and leaves nonspatial pages global', async () => {
  const middleware = (await import('../../app/middleware/geo.global')).default
  const store = useFilterPreferencesStore()
  await middleware(route as never, route as never)
  expect(api.geoArea).not.toHaveBeenCalled()
  await middleware({ ...route, query: { geo_scope_id: geoArea.id } } as never, route as never)
  expect(store.sharedGeoScope).toEqual(geoArea)
  await middleware(route as never, route as never)
  expect(navigate).toHaveBeenLastCalledWith(
    { path: '/events', query: { geo_scope_id: geoArea.id }, hash: '' },
    { replace: true },
  )
  const other = { ...geoArea, id: '10000000-0000-4000-8000-000000000002', name: 'Aarhus' }
  api.geoArea.mockResolvedValueOnce(other)
  await middleware({ ...route, query: { geo_scope_id: other.id } } as never, route as never)
  expect(store.sharedGeoScope?.name).toBe('Aarhus')
  navigate.mockClear()
  await middleware({ ...route, path: '/users' } as never, route as never)
  expect(navigate).not.toHaveBeenCalled()
  expect(supportsGeoScope('/images')).toBe(false)
  expect(supportsGeoScope('/venues/123')).toBe(false)
})
it('removes invalid or unknown scopes with a visible warning, preserves other filters', async () => {
  const middleware = (await import('../../app/middleware/geo.global')).default
  api.geoArea.mockRejectedValue(new AdminApiError(failure(404, 'geo_scope_not_found')))
  for (const scope of ['bad', geoArea.id]) {
    await middleware(
      { ...route, query: { geo_scope_id: scope, period: '90d' } } as never,
      route as never,
    )
    expect(useFilterPreferencesStore().sharedGeoScope).toBeNull()
    expect(useFilterPreferencesStore().geoScopeError).toBeTruthy()
    expect(navigate).toHaveBeenLastCalledWith(
      { path: '/events', query: { period: '90d' }, hash: '' },
      { replace: true },
    )
  }
})
it('does not silently remove a scope on storage failure', async () => {
  const middleware = (await import('../../app/middleware/geo.global')).default
  api.geoArea.mockRejectedValueOnce(new AdminApiError(failure(503)))
  await middleware({ ...route, query: { geo_scope_id: geoArea.id } } as never, route as never)
  expect(navigate).not.toHaveBeenCalled()
  expect(useFilterPreferencesStore().geoScopeError).toBeTruthy()
})
it('does not hydrate an earlier session after logout', async () => {
  const middleware = (await import('../../app/middleware/geo.global')).default
  let resolve!: (area: typeof geoArea) => void
  api.geoArea.mockImplementationOnce(
    () =>
      new Promise((r) => {
        resolve = r
      }),
  )
  const pending = middleware(
    { ...route, query: { geo_scope_id: geoArea.id } } as never,
    route as never,
  )
  auth.revision++
  auth.isAdmin = false
  resolve(geoArea)
  await pending
  expect(useFilterPreferencesStore().sharedGeoScope).toBeNull()
})
function selector() {
  const wrapper = mount(GeoScopeSelector, {
    global: {
      stubs: {
        AppModal: { template: '<div><slot /></div>', methods: { open() {}, close() {} } },
      },
    },
  })
  wrappers.push(wrapper)
  return wrapper
}
it('debounces, aborts stale searches, escapes labels, selects via keyboard and resets only geo', async () => {
  vi.useFakeTimers()
  const wrapper = selector()
  const input = wrapper.get('input')
  await input.setValue('F')
  await vi.advanceTimersByTimeAsync(400)
  expect(api.searchGeoAreas).not.toHaveBeenCalled()
  let resolve!: (value: unknown) => void
  api.searchGeoAreas.mockImplementationOnce(
    () =>
      new Promise((r) => {
        resolve = r
      }),
  )
  await input.setValue('Fl')
  await vi.advanceTimersByTimeAsync(300)
  const signal = api.searchGeoAreas.mock.calls[0]![1] as AbortSignal
  await input.setValue('Flensburg')
  expect(signal.aborted).toBe(true)
  resolve({ items: [{ ...geoSearchItem, name: 'Stale' }] })
  await flushPromises()
  expect(wrapper.text()).not.toContain('Stale')
  api.searchGeoAreas.mockResolvedValueOnce({
    items: [{ ...geoSearchItem, name: '<script>alert(1)</script>' }],
  })
  await vi.advanceTimersByTimeAsync(300)
  expect(wrapper.find('script').exists()).toBe(false)
  expect(wrapper.text()).toContain('<script>alert(1)</script>')
  expect(input.attributes('role')).toBe('combobox')
  route.query = { period: '90d', status: 'draft', page: '4' }
  await input.trigger('keydown', { key: 'ArrowDown' })
  await input.trigger('keydown', { key: 'Enter' })
  await flushPromises()
  expect(api.importGeoArea).toHaveBeenCalledWith({
    source: 'osm',
    source_type: 'relation',
    source_id: '27020',
  })
  expect(route.query).toEqual({
    period: '90d',
    status: 'draft',
    page: '1',
    geo_scope_id: geoArea.id,
  })
  await wrapper.get('[aria-label="Gebiet zurücksetzen"]').trigger('click')
  expect(route.query).toEqual({ period: '90d', status: 'draft', page: '1' })
  expect(useFilterPreferencesStore().sharedGeoScope).toBeNull()
})
it('shows a safe provider-unavailable message', async () => {
  vi.useFakeTimers()
  api.searchGeoAreas.mockRejectedValueOnce(
    new AdminApiError(failure(503, 'geo_provider_unavailable')),
  )
  const wrapper = selector()
  await wrapper.get('input').setValue('Flensburg')
  await vi.advanceTimersByTimeAsync(300)
  expect(wrapper.get('[role="alert"]').text()).toContain('Gespeicherte Gebiete bleiben nutzbar')
})
it('validates responses and sends CSRF plus identity-only area imports', async () => {
  const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify(geoArea)))
  const client = createAdminApi(fetcher)
  await client.importGeoArea({ source: 'osm', source_type: 'relation', source_id: '27020' })
  expect(fetcher.mock.calls[0]![1]).toMatchObject({
    method: 'POST',
    headers: { 'X-Admin-CSRF': '1' },
  })
  expect(geoAreaImportSchema.safeParse({ ...geoArea, geometry: {} }).success).toBe(false)
  fetcher.mockResolvedValueOnce(new Response('{}'))
  await expect(client.geoArea(geoArea.id)).rejects.toThrow()
})
it('proxy allows only declared geo routes, queries and strict import bodies', async () => {
  const fetcher = vi
    .fn<typeof fetch>()
    .mockImplementation(async () => new Response(JSON.stringify(geoArea)))
  const input = {
    path: '/api/v1/geo/areas',
    method: 'POST',
    query: new URLSearchParams(),
    authorization: 'Bearer development',
    origin: 'https://admin.test',
    csrf: '1',
    body: { source: 'osm', source_type: 'relation', source_id: '27020' },
  }
  expect((await forwardAdminRequest(input, 'https://api.test', fetcher)).status).toBe(200)
  expect(fetcher.mock.calls[0]![1]).toMatchObject({
    headers: { Origin: 'https://admin.test', 'X-Admin-CSRF': '1' },
  })
  expect(
    (
      await forwardAdminRequest(
        { ...input, body: { ...input.body, polygon: {} } },
        'https://api.test',
        fetcher,
      )
    ).status,
  ).toBe(422)
  for (const path of ['/api/v1/users', '/api/v1/images', '/api/v1/graph', '/api/v1/notifications'])
    expect(
      (
        await forwardAdminRequest(
          {
            ...input,
            path,
            method: 'GET',
            query: new URLSearchParams({ geo_scope_id: geoArea.id }),
          },
          'https://api.test',
          fetcher,
        )
      ).status,
    ).toBe(422)
  expect(
    (
      await forwardAdminRequest(
        {
          ...input,
          path: '/api/v1/geo/areas/search',
          method: 'GET',
          query: new URLSearchParams({ q: 'Foo', host: 'evil' }),
        },
        'https://api.test',
        fetcher,
      )
    ).status,
  ).toBe(422)
})
