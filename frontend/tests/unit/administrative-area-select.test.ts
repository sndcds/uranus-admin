import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import Select from '../../app/components/AdministrativeAreaSelect.vue'
import { researchArea } from '../fixtures/research'
import { AdminApiError, failure } from '../../shared/errors'
const api = { researchAreas: vi.fn(), researchAreaMetadata: vi.fn() }
const auth = reactive({ canResearch: true, revision: 0 })
const views: ReturnType<typeof mount>[] = []
function view(props = {}) {
  const wrapper = mount(Select, {
    props,
    global: { stubs: { NuxtLink: { template: '<a><slot /></a>' } } },
  })
  views.push(wrapper)
  return wrapper
}
beforeEach(() => {
  vi.useFakeTimers()
  vi.resetAllMocks()
  auth.canResearch = true
  auth.revision = 0
  api.researchAreas.mockResolvedValue({ items: [researchArea] })
  api.researchAreaMetadata.mockResolvedValue(researchArea)
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
  vi.stubGlobal('useAuthStore', () => auth)
})
afterEach(() => {
  views.splice(0).forEach((wrapper) => wrapper.unmount())
  vi.useRealTimers()
  vi.unstubAllGlobals()
})
it('requires two characters, debounces 300ms and bounds the request', async () => {
  const wrapper = view()
  const input = wrapper.get('input')
  await input.setValue(' F ')
  await vi.advanceTimersByTimeAsync(400)
  expect(api.researchAreas).not.toHaveBeenCalled()
  await input.setValue(' Fl ')
  expect(wrapper.get('[role=status]').text()).toContain('gesucht')
  await vi.advanceTimersByTimeAsync(299)
  expect(api.researchAreas).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(1)
  expect(api.researchAreas).toHaveBeenCalledWith(
    { q: 'Fl', page_size: 10 },
    expect.any(AbortSignal),
  )
  expect(wrapper.get('[role=option]').text()).toContain('Deutschland · Schleswig-Holstein')
})
it('suppresses stale searches and aborts on new input and unmount', async () => {
  let resolve!: (value: unknown) => void
  api.researchAreas.mockImplementationOnce(
    () =>
      new Promise((r) => {
        resolve = r
      }),
  )
  const wrapper = view()
  const input = wrapper.get('input')
  await input.setValue('Fl')
  await vi.advanceTimersByTimeAsync(300)
  const signal = api.researchAreas.mock.calls[0]![1] as AbortSignal
  await input.setValue('Sø')
  expect(signal.aborted).toBe(true)
  resolve({ items: [{ ...researchArea, name: 'Stale' }] })
  await flushPromises()
  expect(wrapper.text()).not.toContain('Stale')
  await vi.advanceTimersByTimeAsync(300)
  const next = api.researchAreas.mock.calls[1]![1] as AbortSignal
  wrapper.unmount()
  expect(next.aborted).toBe(true)
})
it.each(['research', 'operations'] as const)(
  'selects by keyboard with accessible active option in %s',
  async (workspace) => {
    api.researchAreas.mockResolvedValue({
      items: [
        researchArea,
        { ...researchArea, id: '40000000-0000-4000-8000-000000000002', name: 'Second' },
      ],
    })
    const wrapper = view({ workspace })
    const input = wrapper.get('input')
    await input.setValue('Fl')
    await vi.advanceTimersByTimeAsync(300)
    expect(input.attributes('aria-expanded')).toBe('true')
    await input.trigger('keydown', { key: 'ArrowUp' })
    expect(wrapper.findAll('[role=option]')[1]!.attributes('aria-selected')).toBe('true')
    expect(input.attributes('aria-activedescendant')).toBe(
      wrapper.findAll('[role=option]')[1]!.attributes('id'),
    )
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')).toEqual([[researchArea.id]])
    expect(wrapper.emitted('select')).toEqual([[researchArea]])
    expect(input.attributes('aria-expanded')).toBe('false')
  },
)
it('Escape cancels pending search without selection', async () => {
  const wrapper = view()
  const input = wrapper.get('input')
  await input.setValue('Fl')
  await input.trigger('keydown', { key: 'Escape' })
  await vi.advanceTimersByTimeAsync(300)
  expect(api.researchAreas).not.toHaveBeenCalled()
  expect(wrapper.emitted('select')).toBeUndefined()
  expect(wrapper.emitted('close')).toHaveLength(1)
})
it('hydrates by ID and clears without a text search', async () => {
  const wrapper = view({ modelValue: researchArea.id })
  await flushPromises()
  expect(api.researchAreaMetadata).toHaveBeenCalledWith(researchArea.id, expect.any(AbortSignal))
  expect(api.researchAreas).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain(researchArea.name)
  await wrapper.get('button').trigger('click')
  expect(wrapper.emitted('update:modelValue')).toEqual([[undefined]])
})
it('auth revision cancels search and hydration, ignoring late values', async () => {
  let selected!: (value: unknown) => void
  let searched!: (value: unknown) => void
  api.researchAreaMetadata.mockImplementationOnce(
    () =>
      new Promise((r) => {
        selected = r
      }),
  )
  api.researchAreas.mockImplementationOnce(
    () =>
      new Promise((r) => {
        searched = r
      }),
  )
  const wrapper = view({ modelValue: researchArea.id })
  await wrapper.get('input').setValue('Fl')
  await vi.advanceTimersByTimeAsync(300)
  auth.canResearch = false
  auth.revision++
  await flushPromises()
  expect((api.researchAreaMetadata.mock.calls[0]![1] as AbortSignal).aborted).toBe(true)
  expect((api.researchAreas.mock.calls[0]![1] as AbortSignal).aborted).toBe(true)
  selected(researchArea)
  searched({ items: [researchArea] })
  await flushPromises()
  expect(wrapper.text()).not.toContain('Flensburg')
})
it('suppresses stale selected-value hydration', async () => {
  let resolve!: (value: unknown) => void
  api.researchAreaMetadata.mockImplementationOnce(
    () =>
      new Promise((r) => {
        resolve = r
      }),
  )
  const wrapper = view({ modelValue: researchArea.id })
  const nextId = '40000000-0000-4000-8000-000000000002'
  api.researchAreaMetadata.mockResolvedValueOnce({ ...researchArea, id: nextId, name: 'Next' })
  await wrapper.setProps({ modelValue: nextId })
  await flushPromises()
  expect((api.researchAreaMetadata.mock.calls[0]![1] as AbortSignal).aborted).toBe(true)
  resolve(researchArea)
  await flushPromises()
  expect(wrapper.text()).toContain('Next')
  expect(wrapper.text()).not.toContain('Flensburg')
})
it('shows empty results and safe catalog failures', async () => {
  api.researchAreas.mockResolvedValueOnce({ items: [] })
  const wrapper = view()
  await wrapper.get('input').setValue('Fl')
  await vi.advanceTimersByTimeAsync(300)
  expect(wrapper.get('[role=status]').text()).toContain('Keine importierten')
  api.researchAreas.mockRejectedValueOnce(new AdminApiError(failure(503, 'database_unavailable')))
  await wrapper.get('input').setValue('Flen')
  await vi.advanceTimersByTimeAsync(300)
  expect(wrapper.get('[role=alert]').text()).toBeTruthy()
  expect(wrapper.find('[role=status]').exists()).toBe(false)
})
