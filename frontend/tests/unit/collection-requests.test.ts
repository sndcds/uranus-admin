import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import * as vue from 'vue'
import Activity from '../../app/pages/activity.vue'
import EntityListPage from '../../app/components/EntityListPage.vue'
import PageHeader from '../../app/components/PageHeader.vue'
import RequestState from '../../app/components/RequestState.vue'
import ResultSummary from '../../app/components/ResultSummary.vue'
import TechnicalInfoBar from '../../app/components/TechnicalInfoBar.vue'
import { activityFixture } from '../fixtures/activity'
import { entityFixture } from '../fixtures/entities'
import { AdminApiError, failure } from '../../shared/errors'

const route = vue.reactive({ path: '/activity', query: {} as Record<string, string> })
const api = { activity: vi.fn(), entities: vi.fn() }
beforeEach(() => {
  vi.resetAllMocks()
  setActivePinia(createPinia())
  route.query = {}
  for (const key of ['ref', 'computed', 'watch', 'onMounted'] as const) vi.stubGlobal(key, vue[key])
  vi.stubGlobal('useRoute', () => route)
  vi.stubGlobal('useRouter', () => ({ replace: vi.fn(), push: vi.fn() }))
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
})
afterEach(() => vi.unstubAllGlobals())

for (const kind of ['activity', 'entities'] as const) {
  it(`${kind} clears changed selections, rejects late responses and removes auth/invalid-query data`, async () => {
    const fixture = kind === 'activity' ? activityFixture : entityFixture('events')
    api[kind].mockResolvedValue(fixture)
    const wrapper = shallowMount(kind === 'activity' ? Activity : EntityListPage, {
      props: { section: 'events' },
      global: {
        components: { PageHeader, RequestState, ResultSummary, TechnicalInfoBar },
        stubs: { PageHeader: false },
      },
    })
    const refresh = () =>
      wrapper
        .findAll('button')
        .find((button) => button.text() === 'Aktualisieren')!
        .trigger('click')
    await flushPromises()
    expect(wrapper.findComponent(TechnicalInfoBar).exists()).toBe(true)
    let resolve!: (value: typeof fixture) => void
    api[kind].mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done
        }),
    )
    await refresh()
    expect(wrapper.findComponent(RequestState).props('hasData')).toBe(true)
    // A different page must not keep the previous page or accept its late refresh.
    route.query = { page: '2' }
    api[kind].mockResolvedValue({ ...fixture, items: [] })
    await flushPromises()
    resolve(fixture)
    await flushPromises()
    expect(wrapper.findComponent(ResultSummary).props('visible')).toBe(0)
    for (const status of [401, 403, 404, 422]) {
      api[kind].mockResolvedValue(fixture)
      await refresh()
      await flushPromises()
      api[kind].mockRejectedValueOnce(new AdminApiError(failure(status)))
      await refresh()
      await flushPromises()
      expect(wrapper.findComponent(ResultSummary).exists()).toBe(false)
    }
    wrapper.unmount()
  })
}
