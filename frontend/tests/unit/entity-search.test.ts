import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import EntitySearch from '../../app/components/EntitySearch.vue'
import { entitySearchResponseSchema } from '../../shared/contracts'
import { entityFixture } from '../fixtures/entities'
import { createAdminApi } from '../../app/utils/admin-api'

const source = entityFixture('users').items[0]!
const item = {
  entity_type: 'user' as const,
  entity_key: source.entity_key,
  label: 'Max Mustermann',
  subtitle: '@max · max@example.org',
  status: 'active',
  action: source.action!,
}
const api = { entitySearch: vi.fn() }
const wrappers: ReturnType<typeof mount>[] = []
function setup() {
  const wrapper = mount(EntitySearch, {
    props: {
      entityType: 'user',
      modelValue: '',
      'onUpdate:modelValue': (value: string) => {
        void wrapper.setProps({ modelValue: value })
      },
    },
    global: { stubs: { AppIcon: true } },
    attachTo: document.body,
  })
  wrappers.push(wrapper)
  return wrapper
}
beforeEach(() => {
  vi.useFakeTimers()
  api.entitySearch.mockReset().mockResolvedValue({ items: [item] })
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
})
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  vi.useRealTimers()
  vi.unstubAllGlobals()
})
it('debounces trimmed input from two characters and shows loading, labels and ARIA', async () => {
  const wrapper = setup(),
    input = wrapper.get('input')
  await input.trigger('focus')
  await input.setValue(' m ')
  await vi.advanceTimersByTimeAsync(500)
  expect(api.entitySearch).not.toHaveBeenCalled()
  await input.setValue('ma')
  await vi.advanceTimersByTimeAsync(200)
  await input.setValue(' max ')
  await vi.advanceTimersByTimeAsync(274)
  expect(api.entitySearch).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('Suche läuft …')
  await vi.advanceTimersByTimeAsync(1)
  expect(api.entitySearch).toHaveBeenCalledExactlyOnceWith({
    q: 'max',
    entity_type: 'user',
    limit: 10,
    organization_id: undefined,
    status: undefined,
  })
  expect(wrapper.text()).toContain('Max Mustermann')
  expect(wrapper.text()).toContain('@max · max@example.org')
  expect(input.attributes('role')).toBe('combobox')
  expect(input.attributes('aria-expanded')).toBe('true')
  expect(input.attributes('aria-controls')).toBe(wrapper.get('[role="listbox"]').attributes('id'))
  expect(input.attributes('aria-activedescendant')).toBeUndefined()
})
it('ignores late successes and failures as soon as input or organization changes', async () => {
  let resolve!: (value: unknown) => void
  let reject!: (value: unknown) => void
  api.entitySearch
    .mockImplementationOnce(
      () =>
        new Promise((r) => {
          resolve = r
        }),
    )
    .mockImplementationOnce(
      () =>
        new Promise((_, r) => {
          reject = r
        }),
    )
    .mockResolvedValue({ items: [{ ...item, label: 'Latest' }] })
  const wrapper = setup(),
    input = wrapper.get('input')
  await input.trigger('focus')
  await input.setValue('ma')
  await vi.advanceTimersByTimeAsync(275)
  await input.setValue('max')
  resolve({ items: [item] })
  await flushPromises()
  expect(wrapper.text()).not.toContain('Max Mustermann')
  await vi.advanceTimersByTimeAsync(275)
  await wrapper.setProps({ organizationId: source.entity_key, status: 'active' })
  await vi.advanceTimersByTimeAsync(275)
  reject(new Error('stale'))
  await flushPromises()
  expect(wrapper.text()).toContain('Latest')
  expect(wrapper.text()).not.toContain('konnte nicht')
  expect(api.entitySearch).toHaveBeenLastCalledWith(
    expect.objectContaining({ organization_id: source.entity_key, status: 'active' }),
  )
})
it('supports arrows, explicit Enter selection, Escape and Enter without selection', async () => {
  api.entitySearch.mockResolvedValue({
    items: [item, { ...item, entity_key: 'second', label: 'Second' }],
  })
  const wrapper = setup(),
    input = wrapper.get('input')
  await input.trigger('focus')
  await input.setValue('max')
  await vi.advanceTimersByTimeAsync(275)
  await input.trigger('keydown', { key: 'ArrowDown' })
  expect(wrapper.findAll('[role="option"]')[0]!.attributes('aria-selected')).toBe('true')
  expect(input.attributes('aria-activedescendant')).toBe(
    wrapper.findAll('[role="option"]')[0]!.attributes('id'),
  )
  await input.trigger('keydown', { key: 'ArrowUp' })
  expect(wrapper.findAll('[role="option"]')[1]!.attributes('aria-selected')).toBe('true')
  await input.trigger('keydown', { key: 'ArrowDown' })
  await input.trigger('keydown', { key: 'Enter' })
  expect(wrapper.emitted('select')).toEqual([[item]])
  expect(wrapper.emitted('apply')).toBeUndefined()
  await input.setValue('maxi')
  await input.trigger('keydown', { key: 'Enter' })
  expect(wrapper.emitted('apply')).toHaveLength(1)
  await input.setValue('max')
  await vi.advanceTimersByTimeAsync(275)
  await input.trigger('keydown', { key: 'Escape' })
  expect(wrapper.props('modelValue')).toBe('')
  expect(input.attributes('aria-expanded')).toBe('false')
  expect(input.attributes('aria-activedescendant')).toBeUndefined()
})
it('clicks select, outside click closes and pending responses cannot reopen', async () => {
  const wrapper = setup(),
    input = wrapper.get('input')
  await input.trigger('focus')
  await input.setValue('max')
  await vi.advanceTimersByTimeAsync(275)
  await wrapper.get('[role="option"]').trigger('click')
  expect(wrapper.emitted('select')).toEqual([[item]])
  await input.setValue('maxi')
  document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }))
  await vi.advanceTimersByTimeAsync(500)
  expect(input.attributes('aria-expanded')).toBe('false')
  expect(api.entitySearch).toHaveBeenCalledTimes(1)
})
it('shows empty and local error states, retries on new input and closes on Tab blur', async () => {
  api.entitySearch.mockResolvedValueOnce({ items: [] }).mockRejectedValueOnce(new Error('secret'))
  const wrapper = setup(),
    input = wrapper.get('input')
  await input.trigger('focus')
  await input.setValue('empty')
  await vi.advanceTimersByTimeAsync(275)
  expect(wrapper.text()).toContain('Keine passenden Datensätze gefunden.')
  await input.setValue('error')
  await vi.advanceTimersByTimeAsync(275)
  expect(wrapper.text()).toContain('Suche konnte nicht geladen werden.')
  expect(wrapper.text()).not.toContain('secret')
  await input.setValue('max')
  await vi.advanceTimersByTimeAsync(275)
  expect(wrapper.text()).toContain(item.label)
  await input.trigger('focusout', { relatedTarget: document.body })
  expect(input.attributes('aria-expanded')).toBe('false')
})
it('validates safe action targets and uses the central API client', async () => {
  expect(entitySearchResponseSchema.safeParse({ items: [item] }).success).toBe(true)
  for (const action of [
    { ...item.action, href: 'https://evil.invalid' },
    { ...item.action, entity_type: 'event' },
  ]) {
    expect(entitySearchResponseSchema.safeParse({ items: [{ ...item, action }] }).success).toBe(
      false,
    )
  }
  expect(entitySearchResponseSchema.safeParse({ items: Array(21).fill(item) }).success).toBe(false)
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [item] })))
  await createAdminApi(fetcher).entitySearch({ entity_type: 'user', q: 'max' })
  expect(fetcher).toHaveBeenCalledWith(
    '/api/admin/api/v1/entity-search?entity_type=user&q=max',
    expect.objectContaining({ method: 'GET', cache: 'no-store' }),
  )
})

it('keeps the newest results when an older request succeeds last', async () => {
  let resolve!: (value: unknown) => void
  api.entitySearch
    .mockImplementationOnce(
      () =>
        new Promise((r) => {
          resolve = r
        }),
    )
    .mockResolvedValue({ items: [{ ...item, label: 'Latest' }] })
  const wrapper = setup(),
    input = wrapper.get('input')
  await input.trigger('focus')
  await input.setValue('ma')
  await vi.advanceTimersByTimeAsync(275)
  await input.setValue('maxi')
  await vi.advanceTimersByTimeAsync(275)
  resolve({ items: [item] })
  await flushPromises()
  expect(wrapper.text()).toContain('Latest')
  expect(wrapper.text()).not.toContain('Max Mustermann')
})
