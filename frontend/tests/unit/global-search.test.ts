import { inspectorHref } from '../../app/utils/inspector'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
import GlobalSearchPalette from '../../app/components/GlobalSearchPalette.vue'
import { globalSearchResponseSchema, type GlobalSearchResponse } from '../../shared/contracts'
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
it('debounces, groups results and opens the inspector using keyboard or pointer', async () => {
  const wrapper = setup()
  await open()
  const input = wrapper.get('input')
  await input.setValue(' p ')
  await vi.advanceTimersByTimeAsync(300)
  expect(api.globalSearch).not.toHaveBeenCalled()
  await input.setValue('person@')
  await vi.advanceTimersByTimeAsync(200)
  await input.setValue('person@example.org')
  expect(wrapper.get('[role="listbox"]').attributes('aria-busy')).toBe('false')
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
    inspectorHref(
      globalSearchFixture('person@example.org').groups[0]!.items[0]!.entity_type,
      globalSearchFixture('person@example.org').groups[0]!.items[0]!.entity_key,
    )!,
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
    inspectorHref(
      globalSearchFixture('Kühlhaus').groups[1]!.items[0]!.entity_type,
      globalSearchFixture('Kühlhaus').groups[1]!.items[0]!.entity_key,
    )!,
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
  expect(wrapper.text()).toContain('Neue Suche konnte nicht geladen werden')
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
  expect(wrapper.text()).toContain('Kühlhaus Flensburg')
  expect(wrapper.text()).not.toContain('person@example.org')
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

function deferredSearch() {
  let resolve!: (data: GlobalSearchResponse) => void
  let reject!: (reason: Error) => void
  const promise = new Promise<GlobalSearchResponse>((ok, fail) => {
    resolve = ok
    reject = fail
  })
  return { promise, resolve, reject }
}

it('retains the successful snapshot through every keystroke, debounce and pending replacement', async () => {
  const wrapper = setup()
  await open()
  const input = wrapper.get('input')
  await input.setValue('Kühlhaus')
  await vi.advanceTimersByTimeAsync(250)
  const pending = deferredSearch()
  api.globalSearch.mockReturnValueOnce(pending.promise)
  for (const text of ['pe', 'per', 'person@']) {
    await input.setValue(text)
    await vi.advanceTimersByTimeAsync(100)
    expect(wrapper.text()).toContain('Kühlhaus Flensburg')
    expect(wrapper.text()).toContain('Datensätze für „Kühlhaus“')
    expect(api.globalSearch).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[role="listbox"]').attributes('aria-busy')).toBe('false')
    expect(document.activeElement).toBe(input.element)
  }
  await vi.advanceTimersByTimeAsync(150)
  expect(api.globalSearch).toHaveBeenCalledTimes(2)
  expect(wrapper.get('[role="listbox"]').attributes('aria-busy')).toBe('true')
  expect(wrapper.text()).toContain('Ergebnisse werden aktualisiert')
  expect(wrapper.text()).toContain('Kühlhaus Flensburg')
  expect(document.activeElement).toBe(input.element)
  pending.resolve(globalSearchFixture('person@'))
  await flushPromises()
  expect(wrapper.text()).not.toContain('Kühlhaus')
  expect(wrapper.text()).toContain('person@example.org')
  expect(wrapper.text()).toContain('Datensätze für „person@“')
  expect(document.activeElement).toBe(input.element)
  expect(input.attributes('aria-activedescendant')).toBe(
    wrapper.get('[role="option"]').attributes('id'),
  )
})

it.each(['', ' a '])(
  'clears remote state below two trimmed characters (%s), ignoring late success',
  async (text) => {
    const wrapper = setup()
    await open()
    const input = wrapper.get('input')
    await input.setValue('Kühlhaus')
    await vi.advanceTimersByTimeAsync(250)
    const pending = deferredSearch()
    api.globalSearch.mockReturnValueOnce(pending.promise)
    await input.setValue('person@')
    await vi.advanceTimersByTimeAsync(250)
    const signal = api.globalSearch.mock.calls[1]![1] as AbortSignal
    await input.setValue(text)
    expect(signal.aborted).toBe(true)
    expect(wrapper.text()).not.toContain('Kühlhaus')
    expect(wrapper.text()).not.toContain('Datensätze für')
    expect(wrapper.get('[role="listbox"]').attributes('aria-busy')).toBe('false')
    expect(wrapper.get('[role="group"]').text()).toContain('Navigation')
    pending.resolve(globalSearchFixture('person@'))
    await flushPromises()
    expect(wrapper.text()).not.toContain('person@example.org')
    expect(document.activeElement).toBe(input.element)
  },
)

it('preserves selected identity as navigation changes and only scrolls on arrow keys', async () => {
  const wrapper = setup()
  await open()
  const input = wrapper.get('input')
  await input.setValue('Kühlhaus')
  await vi.advanceTimersByTimeAsync(250)
  await input.trigger('keydown', { key: 'ArrowDown' })
  expect(wrapper.get('[aria-selected="true"]').text()).toContain('Kühlhaus Flensburg')
  const scroll = vi.fn()
  for (const option of wrapper.findAll('[role="option"]')) option.element.scrollIntoView = scroll
  for (const query of ['Or', 'Orte', 'Kühlhaus neu']) {
    await input.setValue(query)
    expect(wrapper.get('[aria-selected="true"]').text()).toContain('Kühlhaus Flensburg')
    expect(input.attributes('aria-activedescendant')).toBe(
      wrapper.get('[aria-selected="true"]').attributes('id'),
    )
  }
  expect(scroll).not.toHaveBeenCalled()
  await input.trigger('keydown', { key: 'ArrowUp' })
  expect(scroll).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(250)
  expect(wrapper.findAll('[aria-selected="true"]')).toHaveLength(1)
  expect(wrapper.get('[aria-selected="true"]').text()).toContain('Kühlhaus e.V.')
  await input.setValue('no matches')
  await vi.advanceTimersByTimeAsync(250)
  expect(wrapper.find('[role="option"]').exists()).toBe(false)
  expect(input.attributes('aria-activedescendant')).toBeUndefined()
  await input.trigger('keydown', { key: 'ArrowDown' })
  expect(input.attributes('aria-activedescendant')).toBeUndefined()
})

it('keeps successful results and their query on error, then accepts a successful empty response', async () => {
  const wrapper = setup()
  await open()
  const input = wrapper.get('input')
  await input.setValue('Kühlhaus')
  await vi.advanceTimersByTimeAsync(250)
  api.globalSearch.mockRejectedValueOnce(new Error('private error'))
  await input.setValue('unavailable')
  await vi.advanceTimersByTimeAsync(250)
  expect(wrapper.text()).toContain('Neue Suche konnte nicht geladen werden.')
  expect(wrapper.text()).toContain('Datensätze für „Kühlhaus“')
  expect(wrapper.text()).toContain('Kühlhaus Flensburg')
  expect(wrapper.text()).not.toContain('private error')
  expect(document.activeElement).toBe(input.element)
  await input.setValue('missing')
  await vi.advanceTimersByTimeAsync(250)
  expect(wrapper.text()).not.toContain('Kühlhaus')
  expect(wrapper.text()).not.toContain('Neue Suche konnte')
  expect(wrapper.text()).toContain('Keine passenden Ergebnisse')
  expect(wrapper.text()).toContain('Datensätze für „missing“')
})

it('closing clears the successful snapshot and pending state, even after a late response', async () => {
  const wrapper = setup()
  await open()
  await wrapper.get('input').setValue('Kühlhaus')
  await vi.advanceTimersByTimeAsync(250)
  const pending = deferredSearch()
  api.globalSearch.mockReturnValueOnce(pending.promise)
  await wrapper.get('input').setValue('person@')
  await vi.advanceTimersByTimeAsync(250)
  const signal = api.globalSearch.mock.calls[1]![1] as AbortSignal
  await wrapper.get('input').trigger('keydown', { key: 'Escape' })
  expect(signal.aborted).toBe(true)
  await open()
  pending.resolve(globalSearchFixture('person@'))
  await flushPromises()
  expect(wrapper.get('input').element.value).toBe('')
  expect(wrapper.findAll('[role="option"]')).toHaveLength(adminNavigationItems.length)
  expect(wrapper.text()).not.toContain('Datensätze für')
  expect(wrapper.text()).not.toContain('Kühlhaus')
  expect(wrapper.text()).not.toContain('person@example.org')
  expect(wrapper.get('[role="listbox"]').attributes('aria-busy')).toBe('false')
  expect(wrapper.get('[role="status"]').text()).toBe('')
})

it('renders nine groups with existing icons and navigates across every group boundary', async () => {
  const { allGlobalSearchFixture } = await import('../fixtures/search')
  const data = allGlobalSearchFixture()
  api.globalSearch.mockResolvedValue(data)
  const wrapper = setup()
  await open()
  await wrapper.get('input').setValue(data.query)
  await vi.advanceTimersByTimeAsync(250)
  expect(wrapper.findAll('[role="group"]').map((group) => group.text())).toEqual([
    expect.stringContaining('Benutzer'),
    expect.stringContaining('Organisationen'),
    expect.stringContaining('Orte'),
    expect.stringContaining('Räume'),
    expect.stringContaining('Veranstaltungen'),
    expect.stringContaining('Termine'),
    expect.stringContaining('Bilder'),
    expect.stringContaining('Partneranfragen'),
    expect.stringContaining('Teameinladungen'),
  ])
  expect(
    wrapper.findAll('[role="option"] app-icon-stub').map((icon) => icon.attributes('name')),
  ).toEqual([
    'user',
    'organization',
    'pin',
    'space',
    'calendar',
    'clock',
    'image',
    'partner',
    'users',
  ])
  for (let index = 0; index < data.groups.length; index++) {
    expect(wrapper.get('[aria-selected="true"]').text()).toContain(
      data.groups[index]!.items[0]!.label,
    )
    await wrapper.get('input').trigger('keydown', { key: 'ArrowDown' })
  }
  await wrapper.get('input').trigger('keydown', { key: 'ArrowUp' })
  await wrapper.get('input').trigger('keydown', { key: 'Enter' })
  expect(navigate).toHaveBeenLastCalledWith(
    inspectorHref(data.groups[8]!.items[0]!.entity_type, data.groups[8]!.items[0]!.entity_key)!,
  )
})

it.each([5, 7, 8])('validates API actions and opens the inspector at group %i', async (index) => {
  const { allGlobalSearchFixture } = await import('../fixtures/search')
  const data = allGlobalSearchFixture()
  expect(globalSearchResponseSchema.safeParse(data).success).toBe(true)
  api.globalSearch.mockResolvedValue(data)
  const wrapper = setup()
  await open()
  await wrapper.get('input').setValue(data.query)
  await vi.advanceTimersByTimeAsync(250)
  for (let step = 0; step < index; step++)
    await wrapper.get('input').trigger('keydown', { key: 'ArrowDown' })
  await wrapper.get('input').trigger('keydown', { key: 'Enter' })
  expect(navigate).toHaveBeenCalledWith(
    inspectorHref(
      data.groups[index]!.items[0]!.entity_type,
      data.groups[index]!.items[0]!.entity_key,
    )!,
  )
  const item = data.groups[index]!.items[0]!
  for (const href of ['https://evil.invalid', '/event_dates/' + item.entity_key, '/queues/other']) {
    const bad = structuredClone(data)
    bad.groups[index]!.items[0]!.action.href = href
    expect(globalSearchResponseSchema.safeParse(bad).success).toBe(false)
  }
})

it('keeps collection types restricted and rejects mismatched workflow keys and targets', async () => {
  const { allGlobalSearchFixture } = await import('../fixtures/search')
  const { entitySearchTypeSchema } = await import('../../shared/contracts')
  for (const type of ['event_date', 'partner_request', 'team_membership'])
    expect(entitySearchTypeSchema.safeParse(type).success).toBe(false)
  for (const index of [7, 8]) {
    const data = allGlobalSearchFixture()
    const item = data.groups[index]!.items[0]!
    item.entity_key = 'invalid-key'
    expect(globalSearchResponseSchema.safeParse(data).success).toBe(false)
  }
})
