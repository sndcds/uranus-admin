import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
import GlobalSearchPalette from '../../app/components/GlobalSearchPalette.vue'
import { globalSearchResponseSchema } from '../../shared/contracts'
import { globalSearchFixture } from '../fixtures/search'
import { adminNavigationItems } from '../../app/utils/navigation'
import { createAdminApi } from '../../app/utils/admin-api'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'
const api = { globalSearch: vi.fn() }
const auth = reactive({ isAdmin: true, revision: 0, loggingOut: false })
const route = reactive({ path: '/' })
const navigate = vi.fn()
const wrappers: ReturnType<typeof mount>[] = []
function setup() {
  const wrapper = mount(GlobalSearchPalette, {
    attachTo: document.body,
    global: { stubs: { AppIcon: true } },
  })
  wrappers.push(wrapper)
  return wrapper
}
async function open(modifier = 'ctrlKey') {
  document.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'k', [modifier]: true, bubbles: true, cancelable: true }),
  )
  await flushPromises()
}
beforeEach(() => {
  vi.useFakeTimers()
  Object.assign(auth, { isAdmin: true, revision: 0, loggingOut: false })
  route.path = '/'
  api.globalSearch
    .mockReset()
    .mockImplementation(({ q }: { q: string }) => Promise.resolve(globalSearchFixture(q)))
  navigate.mockReset()
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
  vi.stubGlobal('useAuthStore', () => auth)
  vi.stubGlobal('useRoute', () => route)
  vi.stubGlobal('navigateTo', navigate)
  vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function () {
    this.open = true
  })
  vi.spyOn(HTMLDialogElement.prototype, 'close').mockImplementation(function () {
    this.open = false
  })
})
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  document.body.replaceChildren()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})
it.each(['ctrlKey', 'metaKey'])(
  'opens with %s+K, focuses search and restores the trigger without editing it',
  async (modifier) => {
    const trigger = document.createElement('input')
    trigger.value = 'keep this text'
    document.body.append(trigger)
    trigger.focus()
    const wrapper = setup()
    await open(modifier)
    expect(wrapper.get('dialog').element.open).toBe(true)
    expect(document.activeElement).toBe(wrapper.get('input').element)
    expect(wrapper.get('dialog').attributes('aria-modal')).toBe('true')
    expect(wrapper.findAll('[role="option"]')).toHaveLength(adminNavigationItems.length)
    expect(api.globalSearch).not.toHaveBeenCalled()
    await wrapper.get('input').trigger('keydown', { key: 'Escape' })
    expect(wrapper.get('dialog').element.open).toBe(false)
    expect(document.activeElement).toBe(trigger)
    expect(trigger.value).toBe('keep this text')
  },
)
it('debounces, groups results and follows server Action.href using keyboard or pointer', async () => {
  const wrapper = setup()
  await open()
  const input = wrapper.get('input')
  await input.setValue(' p ')
  await vi.advanceTimersByTimeAsync(300)
  expect(api.globalSearch).not.toHaveBeenCalled()
  await input.setValue('person@')
  await vi.advanceTimersByTimeAsync(200)
  await input.setValue('person@example.org')
  expect(wrapper.text()).toContain('Suche läuft')
  await vi.advanceTimersByTimeAsync(249)
  expect(api.globalSearch).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(1)
  expect(api.globalSearch).toHaveBeenCalledExactlyOnceWith(
    { q: 'person@example.org' },
    expect.any(AbortSignal),
  )
  const option = wrapper.get('[role="option"]')
  expect(option.text()).toContain('person@example.org')
  expect(option.attributes('aria-selected')).toBe('true')
  expect(input.attributes('aria-activedescendant')).toBe(option.attributes('id'))
  await input.trigger('keydown', { key: 'Enter' })
  expect(navigate).toHaveBeenCalledWith(
    globalSearchFixture('person@example.org').groups[0]!.items[0]!.action.href,
  )
  expect(wrapper.find('input').exists()).toBe(false)
  await open()
  await wrapper.get('input').setValue('Kühlhaus')
  await vi.advanceTimersByTimeAsync(250)
  expect(wrapper.findAll('[role="group"]')).toHaveLength(2)
  expect(wrapper.text()).toContain('Organisationen')
  expect(wrapper.text()).toContain('Orte')
  await wrapper.get('input').trigger('keydown', { key: 'ArrowDown' })
  expect(wrapper.findAll('[role="option"]')[1]!.attributes('aria-selected')).toBe('true')
  await wrapper.get('input').trigger('keydown', { key: 'ArrowUp' })
  expect(wrapper.findAll('[role="option"]')[0]!.attributes('aria-selected')).toBe('true')
  await wrapper.findAll('[role="option"]')[1]!.trigger('click')
  expect(navigate).toHaveBeenLastCalledWith(
    globalSearchFixture('Kühlhaus').groups[1]!.items[0]!.action.href,
  )
})
it('finds local navigation, preserves Tab and reports empty/error states', async () => {
  const wrapper = setup()
  await open()
  const input = wrapper.get('input')
  await input.setValue('Arbeitsliste')
  const event = new KeyboardEvent('keydown', { key: 'Tab', cancelable: true })
  input.element.dispatchEvent(event)
  expect(event.defaultPrevented).toBe(false)
  await input.trigger('keydown', { key: 'Enter' })
  expect(navigate).toHaveBeenCalledWith('/findings')
  await open()
  await wrapper.get('input').setValue('missing')
  await vi.advanceTimersByTimeAsync(250)
  expect(wrapper.text()).toContain('Keine passenden Ergebnisse')
  api.globalSearch.mockRejectedValueOnce(new Error('private source error'))
  await wrapper.get('input').setValue('error')
  await vi.advanceTimersByTimeAsync(250)
  expect(wrapper.text()).toContain('Suche konnte nicht geladen werden')
  expect(wrapper.text()).not.toContain('private source error')
})
it('aborts and ignores late successes and mismatched response queries', async () => {
  let resolve!: (data: unknown) => void
  api.globalSearch.mockReturnValueOnce(
    new Promise((r) => {
      resolve = r
    }),
  )
  const wrapper = setup()
  await open()
  await wrapper.get('input').setValue('old@example.org')
  await vi.advanceTimersByTimeAsync(250)
  const signal = api.globalSearch.mock.calls[0]![1] as AbortSignal
  await wrapper.get('input').setValue('Kühlhaus')
  expect(signal.aborted).toBe(true)
  await vi.advanceTimersByTimeAsync(250)
  resolve(globalSearchFixture('old@example.org'))
  await flushPromises()
  expect(wrapper.text()).not.toContain('person@example.org')
  expect(wrapper.text()).toContain('Kühlhaus')
  api.globalSearch.mockResolvedValueOnce(globalSearchFixture('other@example.org'))
  await wrapper.get('input').setValue('new@example.org')
  await vi.advanceTimersByTimeAsync(250)
  expect(wrapper.find('[role="option"]').exists()).toBe(false)
})
it.each(['logout', 'session', 'route', 'revision'])(
  'clears and invalidates results on %s',
  async (reason) => {
    let reject!: (error: unknown) => void
    api.globalSearch.mockReturnValueOnce(
      new Promise((_r, r) => {
        reject = r
      }),
    )
    const wrapper = setup()
    await open()
    await wrapper.get('input').setValue('person@example.org')
    await vi.advanceTimersByTimeAsync(250)
    if (reason === 'logout') auth.loggingOut = true
    else if (reason === 'session') auth.isAdmin = false
    else if (reason === 'route') route.path = '/users'
    else auth.revision++
    await flushPromises()
    reject(new Error('late'))
    await flushPromises()
    expect(wrapper.get('dialog').element.open).toBe(false)
    expect(wrapper.find('input').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('person@example.org')
  },
)
it('validates global limits, group identities, fields and actions through the client', async () => {
  const data = globalSearchFixture('person@example.org')
  expect(globalSearchResponseSchema.safeParse(data).success).toBe(true)
  const item = data.groups[0]!.items[0]!
  for (const change of [
    { action: { ...item.action, href: 'https://evil.invalid' } },
    { matched_fields: ['password_hash'] },
    { entity_type: 'venue' },
  ]) {
    expect(
      globalSearchResponseSchema.safeParse({
        ...data,
        groups: [{ entity_type: 'user', items: [{ ...item, ...change }] }],
      }).success,
    ).toBe(false)
  }
  for (const groups of [
    [data.groups[0], data.groups[0]],
    [{ entity_type: 'user', items: Array(11).fill(item) }],
  ]) {
    expect(globalSearchResponseSchema.safeParse({ ...data, groups }).success).toBe(false)
  }
  const fetcher = vi.fn().mockResolvedValue(Response.json(data))
  const client = createAdminApi(fetcher)
  await client.globalSearch({ q: data.query })
  expect(client.viewRead('/api/v1/search')).toBeUndefined()
  expect(fetcher).toHaveBeenCalledWith(
    '/api/admin/api/v1/search?q=person%40example.org',
    expect.objectContaining({ method: 'GET', cache: 'no-store' }),
  )
  fetcher.mockResolvedValue(Response.json({ groups: [] }))
  await expect(client.globalSearch({ q: data.query })).rejects.toThrow()
})
it('only proxies the exact route, method and unique query keys', async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json({ groups: [] }))
  const base = {
    path: '/api/v1/search',
    method: 'GET',
    authorization: 'Bearer test-credential',
    query: new URLSearchParams('q=max&limit_per_type=5&types=user,venue'),
  }
  expect((await forwardAdminRequest(base, 'http://127.0.0.1:8000', fetcher)).status).toBe(200)
  for (const query of ['q=aa&q=bb', 'q=max&geo_scope_id=ignored', 'q=max&sql=anything']) {
    expect(
      (
        await forwardAdminRequest(
          { ...base, query: new URLSearchParams(query) },
          'http://127.0.0.1:8000',
          fetcher,
        )
      ).status,
    ).toBe(422)
  }
  expect(
    (await forwardAdminRequest({ ...base, method: 'POST' }, 'http://127.0.0.1:8000', fetcher))
      .status,
  ).toBe(405)
  expect(
    (
      await forwardAdminRequest(
        { ...base, authorization: undefined },
        'http://127.0.0.1:8000',
        fetcher,
      )
    ).status,
  ).toBe(401)
})
it('does not persist or retain a query after reopening', async () => {
  const local = vi.spyOn(Storage.prototype, 'setItem')
  const wrapper = setup()
  await open()
  await wrapper.get('input').setValue('person@example.org')
  await vi.advanceTimersByTimeAsync(250)
  await wrapper.get('input').trigger('keydown', { key: 'Escape' })
  await open()
  expect(wrapper.get('input').element.value).toBe('')
  expect(local).not.toHaveBeenCalled()
})

it('handles the global shortcut before editor handlers without taking Shift shortcuts', async () => {
  const wrapper = setup()
  const editor = document.createElement('input')
  editor.value = 'SQL remains intact'
  document.body.append(editor)
  editor.focus()
  const editingShortcut = vi.fn((event: KeyboardEvent) => {
    editor.value = ''
    event.stopPropagation()
  })
  editor.addEventListener('keydown', editingShortcut)
  editor.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true, cancelable: true }),
  )
  await flushPromises()
  expect(editingShortcut).not.toHaveBeenCalled()
  expect(editor.value).toBe('SQL remains intact')
  expect(wrapper.get('dialog').element.open).toBe(true)
  await wrapper.get('input').trigger('keydown', { key: 'Escape' })
  document.dispatchEvent(
    new KeyboardEvent('keydown', { key: 'K', ctrlKey: true, shiftKey: true, bubbles: true }),
  )
  await flushPromises()
  expect(wrapper.get('dialog').element.open).toBe(false)
})
