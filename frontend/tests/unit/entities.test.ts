import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { reactive, ref, nextTick } from 'vue'
import EntityListPage from '../../app/components/EntityListPage.vue'
import EntityDetailPage from '../../app/components/EntityDetailPage.vue'
import FilterBar from '../../app/components/FilterBar.vue'
import PaginationBar from '../../app/components/PaginationBar.vue'
import ResultSummary from '../../app/components/ResultSummary.vue'
import PageHeader from '../../app/components/PageHeader.vue'
import DetailFacts from '../../app/components/DetailFacts.vue'
import { entitySectionSchema, entityPageSchema } from '../../shared/contracts'
import { entityFixture, detailFixture } from '../fixtures/entities'
const api = { entities: vi.fn(), entity: vi.fn() },
  push = vi.fn()
const route = reactive({
  query: {} as Record<string, string>,
  params: { id: entityFixture('events').items[0]!.entity_key },
  fullPath: '/events',
})
const global = {
  components: { FilterBar, PaginationBar, ResultSummary, PageHeader },
  stubs: {
    NuxtLink: { props: ['to'], template: '<a :data-to="JSON.stringify(to)"><slot /></a>' },
    DataListShell: { template: '<ul><slot /></ul>' },
    ActivityRow: { props: ['item'], template: '<li>{{item.entity_name}}</li>' },
    RequestState: {
      props: ['loading', 'error'],
      template: '<div>{{loading ? "loading" : error ? "error" : ""}}</div>',
    },
    EmptyState: { props: ['message'], template: '<p>{{message}}</p>' },
  },
}
beforeEach(() => {
  vi.clearAllMocks()
  route.query = {}
  vi.stubGlobal('useRoute', () => route)
  vi.stubGlobal('useRouter', () => ({ push }))
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
  vi.stubGlobal('useState', () => ref(0))
})
afterEach(() => vi.unstubAllGlobals())
it.each(entitySectionSchema.options)(
  'renders and filters %s, with a paginated safe detail',
  async (section) => {
    const fixture = entityFixture(section)
    expect(entityPageSchema.safeParse(fixture).success).toBe(true)
    let resolveFirst!: (value: typeof fixture) => void
    api.entities
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveFirst = resolve
          }),
      )
      .mockResolvedValue(fixture)
    api.entity.mockResolvedValue(detailFixture(section))
    const list = mount(EntityListPage, { props: { section }, global })
    await nextTick()
    expect(list.text()).toContain('loading')
    resolveFirst(fixture)
    await flushPromises()
    expect(list.text()).toContain(`Fixture ${section}`)
    expect(list.text()).toContain('26 Datensätze insgesamt')
    expect(list.text()).toContain('Seite 1 von 2')
    await list.get('input[type="search"]').setValue('Nord')
    await list.get('form').trigger('submit')
    expect(push).toHaveBeenCalledWith({
      query: { q: 'Nord', organization_id: undefined, status: undefined, page: '1' },
    })
    route.query = { page: '2' }
    await flushPromises()
    expect(api.entities).toHaveBeenLastCalledWith(section, { page: '2' })
    api.entities.mockResolvedValue({
      ...fixture,
      items: [],
      pagination: { ...fixture.pagination, total: 0, pages: 0 },
    })
    route.query = { q: 'missing' }
    await flushPromises()
    expect(list.text()).toContain('Keine Datensätze')
    api.entities.mockRejectedValue(new Error('private'))
    route.query = {}
    await flushPromises()
    expect(list.text()).toContain('error')
    expect(list.text()).not.toContain(`Fixture ${section}`)
    list.unmount()
    const detail = mount(EntityDetailPage, { props: { section }, global })
    await flushPromises()
    expect(detail.text()).toContain(`Fixture ${section}`)
    expect(detail.findAllComponents(PageHeader)).toHaveLength(1)
    expect(detail.findAllComponents(DetailFacts)).toHaveLength(1)
    expect(detail.findAll('dl')).toHaveLength(1)
    const header = detail.getComponent(PageHeader)
    expect(header.get('a').text()).toBe('Zur Liste')
    expect(header.get('a').attributes('data-to')).toBe(JSON.stringify(`/${section}`))
    expect(header.text()).toContain('Befunde zu diesem Datensatz')
    expect(header.find('ul').exists()).toBe(false)
    if (section === 'events') {
      expect(detail.text()).toContain('Standardort')
      expect(detail.text()).toContain('Standardraum')
      expect(detail.text()).toContain('Standardbühne')
    }
    expect(detail.findAll('a').some((a) => a.attributes('data-to')?.includes('entity_key'))).toBe(
      true,
    )
    detail.unmount()
  },
)
