import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import * as vue from 'vue'
import Marks from '../../app/pages/marks/index.vue'
import FilterBar from '../../app/components/FilterBar.vue'
import RequestState from '../../app/components/RequestState.vue'
import InlineAlert from '../../app/components/InlineAlert.vue'
import RecordSection from '../../app/components/RecordSection.vue'
import TechnicalInfoBar from '../../app/components/TechnicalInfoBar.vue'
import DataListShell from '../../app/components/DataListShell.vue'
import MarkFields from '../../app/components/MarkFields.vue'
import EmptyState from '../../app/components/EmptyState.vue'
import { workflowMarks } from '../fixtures/operations-workflows'
import { AdminApiError, failure } from '../../shared/errors'

const route = vue.reactive({ query: {} as Record<string, unknown> })
const marks = vi.fn()
const createMark = vi.fn()
const push = vi.fn()
const fixture = { items: workflowMarks, pagination: { page: 1, page_size: 50, total: 4, pages: 1 } }
const views: { unmount: () => void }[] = []
beforeEach(() => {
  vi.clearAllMocks()
  route.query = {}
  marks.mockResolvedValue(fixture)
  for (const key of ['ref', 'computed', 'watch', 'onMounted', 'onBeforeUnmount'] as const)
    vi.stubGlobal(key, vue[key])
  vi.stubGlobal('useRoute', () => route)
  vi.stubGlobal('useRouter', () => ({ push }))
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: { marks, createMark } }))
})
afterEach(() => {
  views.splice(0).forEach((view) => view.unmount())
  vi.unstubAllGlobals()
})
async function render() {
  const view = mount(Marks, {
    global: {
      components: {
        FilterBar,
        RequestState,
        InlineAlert,
        RecordSection,
        TechnicalInfoBar,
        DataListShell,
        MarkFields,
        EmptyState,
      },
      stubs: {
        NuxtLink: { props: ['to'], template: '<a><slot /></a>' },
        PageHeader: { template: '<header><slot /></header>' },
        ResultSummary: true,
        EntityTypeBadge: true,
        StatusBadge: true,
        AppIcon: true,
        PaginationBar: true,
      },
    },
  })
  views.push(view)
  await flushPromises()
  return view
}
it('retains only same-query results while refreshing, labels errors, and clears denied responses', async () => {
  const view = await render()
  const refresh = () =>
    view
      .findAll('button')
      .find((el) => el.text() === 'Aktualisieren')!
      .trigger('click')
  marks.mockRejectedValueOnce(new AdminApiError(failure(503)))
  await refresh()
  await flushPromises()
  expect(view.text()).toContain('Kulturnacht am Hafen')
  expect(view.text()).toContain('veraltet')
  let resolve!: (result: typeof fixture) => void
  marks.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done
      }),
  )
  route.query = { status: 'done' }
  await flushPromises()
  expect(view.text()).not.toContain('Kulturnacht am Hafen')
  route.query = { status: 'open' }
  await flushPromises()
  resolve({ ...fixture, items: [{ ...workflowMarks[0]!, entity_name: 'Obsolete Antwort' }] })
  await flushPromises()
  expect(view.text()).not.toContain('Obsolete Antwort')
  for (const status of [403, 401]) {
    await refresh()
    await flushPromises()
    marks.mockRejectedValueOnce(new AdminApiError(failure(status)))
    await refresh()
    await flushPromises()
    expect(view.text()).not.toContain('Kulturnacht am Hafen')
    expect(view.findComponent(EmptyState).exists()).toBe(false)
  }
})
it('preserves exact scoped filters and reset, with no invented data timestamp', async () => {
  const scope = { entity_type: 'event', entity_key: workflowMarks[0]!.entity_key }
  route.query = {
    ...scope,
    status: 'done',
    urgency: 'high',
    reason: 'incorrect',
    sort: 'newest',
    page: '2',
  }
  const view = await render()
  expect(marks).toHaveBeenCalledWith(route.query)
  const form = view.get('form[aria-label="Filter"]')
  expect(form.findAll('select').map((el) => (el.element as HTMLSelectElement).value)).toEqual([
    'done',
    'high',
    'incorrect',
    'newest',
  ])
  await form.trigger('submit')
  expect(push).toHaveBeenLastCalledWith({ query: { ...route.query, page: '1' } })
  await form
    .findAll('button')
    .find((el) => el.text() === 'Filter zurücksetzen')!
    .trigger('click')
  expect(push).toHaveBeenLastCalledWith({ query: scope })
  expect(view.getComponent(TechnicalInfoBar).text()).not.toMatch(/Datenstand|Abrufzeit/)
})
it('creates a scoped concern only after reason and other explanation validation', async () => {
  route.query = { entity_type: 'event', entity_key: workflowMarks[0]!.entity_key }
  createMark.mockResolvedValue(workflowMarks[0])
  const view = await render()
  await view.get('button[aria-controls="mark-create"]').trigger('click')
  const form = view.get('#mark-create')
  await form.trigger('submit')
  await flushPromises()
  expect(createMark).not.toHaveBeenCalled()
  expect(view.get('[role="alert"]').text()).toContain('mindestens einen Grund')
  await form.get('input[value="other"]').setValue(true)
  await form.trigger('submit')
  await flushPromises()
  expect(createMark).not.toHaveBeenCalled()
  await form.get('textarea[maxlength="2000"]').setValue('Manuelles Anliegen')
  await form.trigger('submit')
  await flushPromises()
  expect(createMark).toHaveBeenCalledWith({
    ...route.query,
    reasons: ['other'],
    reason_detail: 'Manuelles Anliegen',
    urgency: 'normal',
    note: null,
  })
  expect(push).toHaveBeenLastCalledWith(`/marks/${workflowMarks[0]!.id}`)
})
