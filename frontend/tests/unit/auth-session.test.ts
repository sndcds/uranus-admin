import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useFilterPreferencesStore } from '../../app/stores/filter-preferences'
import { useAuthStore } from '../../app/stores/auth'
import { useDashboardStore } from '../../app/stores/dashboard'
import { useFindingsStore } from '../../app/stores/findings'
import { createAdminApi } from '../../app/utils/admin-api'
import { internalRedirect, returnTarget } from '../../app/utils/auth-redirect'
import { AdminApiError, failure } from '../../shared/errors'
import { findings, summary } from '../fixtures/api'

const principal = { subject: 'admin:fixture', system_admin: true }
let api: ReturnType<typeof createAdminApi>
const navigate = vi.fn()
beforeEach(() => {
  setActivePinia(createPinia())
  api = {
    ...createAdminApi(),
    session: vi.fn().mockResolvedValue(principal),
    login: vi.fn().mockResolvedValue(principal),
    logout: vi.fn().mockResolvedValue({ status: 'ok' }),
  }
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
  vi.stubGlobal('navigateTo', navigate.mockReset())
})
afterEach(() => vi.unstubAllGlobals())

it('deduplicates checks, hydrates only safe state, and reuses confirmed sessions', async () => {
  const auth = useAuthStore()
  const first = auth.checkSession()
  expect(auth.status).toBe('checking')
  await Promise.all([first, auth.checkSession()])
  expect(api.session).toHaveBeenCalledOnce()
  expect(auth.isAdmin).toBe(true)
  await auth.checkSession()
  expect(api.session).toHaveBeenCalledOnce()
  expect(JSON.stringify(auth.$state)).not.toMatch(/token|password|pending/)
})
it('rejects a late check after clearing the session', async () => {
  let resolve!: (value: typeof principal) => void
  api.session = vi.fn().mockReturnValue(
    new Promise((r) => {
      resolve = r
    }),
  )
  const auth = useAuthStore()
  const pending = auth.checkSession()
  auth.clear()
  resolve(principal)
  await pending
  expect(auth.status).toBe('anonymous')
  expect(auth.session).toBeNull()
})
it.each([false, true])('logout clears caches and navigates even on failure: %s', async (fails) => {
  const auth = useAuthStore()
  await auth.checkSession()
  const dashboard = useDashboardStore(),
    list = useFindingsStore()
  const preferences = useFilterPreferencesStore()
  preferences.entities.events.q = 'email@example.org'
  preferences.entities.events.status = 'released'
  preferences.graph.organization = 'private-org'
  preferences.sharedPeriod = '90d'
  dashboard.data = summary
  list.data = findings
  if (fails) api.logout = vi.fn().mockRejectedValue(new Error('private details'))
  await auth.logout()
  expect(api.logout).toHaveBeenCalledOnce()
  expect(auth.status).toBe('anonymous')
  expect(dashboard.data).toBeNull()
  expect(list.data).toBeNull()
  expect(preferences.entities.events).toEqual({ q: '', status: '', temporal: '' })
  expect(preferences.graph.organization).toBe('')
  expect(preferences.sharedPeriod).toBe('24h')
  expect(navigate).toHaveBeenCalledWith('/login', { replace: true })
  expect(Boolean(auth.logoutWarning)).toBe(fails)
  expect(auth.logoutWarning).not.toContain('private details')
})
it.each([401, 403, 503])('fails closed for session response %i', async (status) => {
  api.session = vi.fn().mockRejectedValue(new AdminApiError(failure(status)))
  const auth = useAuthStore()
  await auth.checkSession()
  expect(auth.isAdmin).toBe(false)
  expect(auth.status).toBe(status === 403 ? 'authenticated' : 'anonymous')
})
it('checks the server session after login, with no token in state', async () => {
  const auth = useAuthStore()
  await auth.login('operator', 'synthetic-secret')
  expect(api.login).toHaveBeenCalledWith('operator', 'synthetic-secret')
  expect(api.session).toHaveBeenCalledOnce()
  expect(auth.isAdmin).toBe(true)
  expect(JSON.stringify(auth.$state)).not.toContain('synthetic-secret')
})
it.each([
  'https://evil.example',
  '//evil.example',
  '/folder/..//evil.example',
  '/%2e%2e//evil.example',
  'javascript:alert(1)',
  '/\\evil.example',
  '/%2fevil.example',
  '/\nevil.example',
  '/login',
  '/foo/../login',
  ['/activity'],
])('rejects redirect %s', (value) => {
  expect(internalRedirect(value)).toBe('/')
})
it.each([
  '/',
  '/activity',
  '/events/abc',
  '/graph?root_type=event&root_key=abc&depth=2',
  '/#open-queues',
])('preserves internal target %s', (value) => {
  expect(internalRedirect(value)).toBe(value)
})
it('restores a fragment inherited across the HTTP redirect', () => {
  expect(returnTarget('/activity?period=7d', '#details')).toBe('/activity?period=7d#details')
  expect(returnTarget('/#open-queues', '#other')).toBe('/#open-queues')
})
it('only protected 401 responses signal session loss; 403 and invalid login do not', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response('{}', { status: 403 }))
  const client = createAdminApi(fetcher),
    lost = vi.fn()
  client.onAccessLost(lost)
  await client.summary('24h').catch(() => {})
  expect(lost).not.toHaveBeenCalled()
  fetcher.mockResolvedValue(new Response('{}', { status: 401 }))
  await client.login('user', 'wrong').catch(() => {})
  await client.session().catch(() => {})
  expect(lost).not.toHaveBeenCalled()
  await client.summary('24h').catch(() => {})
  expect(lost).toHaveBeenCalledExactlyOnceWith(401)
})
it.each([
  ['anonymous', false, '/events/abc?tab=x#details', false, '/login'],
  ['anonymous', false, '/login', true, null],
  ['authenticated', true, '/events/abc', false, null],
  ['authenticated', true, '/login', true, '/'],
  ['unknown', false, '/future-route', false, '/login'],
])('middleware: %s, %s, %s', async (status, isAdmin, fullPath, publicRoute, redirect) => {
  vi.stubGlobal('defineNuxtRouteMiddleware', (fn: unknown) => fn)
  const auth = { status, isAdmin, checkSession: vi.fn() }
  vi.stubGlobal('useAuthStore', () => auth)
  const { default: middleware } = await import('../../app/middleware/auth.global')
  await middleware(
    {
      path: fullPath.split(/[?#]/)[0],
      fullPath,
      query: {},
      meta: { public: publicRoute },
    } as never,
    {} as never,
  )
  expect(auth.checkSession).toHaveBeenCalledOnce()
  if (!redirect) expect(navigate).not.toHaveBeenCalled()
  else if (redirect === '/') expect(navigate).toHaveBeenCalledWith('/', { replace: true })
  else
    expect(navigate).toHaveBeenCalledWith(
      { path: '/login', query: { redirect: fullPath } },
      { replace: true },
    )
})
it('central access-loss handler resets stores and preserves the current route', async () => {
  vi.stubGlobal('defineNuxtPlugin', (plugin: unknown) => plugin)
  const auth = useAuthStore()
  await auth.checkSession()
  useDashboardStore().data = summary
  useFindingsStore().data = findings
  vi.stubGlobal('useAuthStore', () => auth)
  vi.stubGlobal('useRouter', () => ({
    currentRoute: { value: { path: '/statistics', fullPath: '/statistics?period=7d' } },
  }))
  const register = vi.spyOn(api, 'onAccessLost')
  const { default: plugin } = await import('../../app/plugins/auth')
  const setup = (plugin as unknown as { setup: (app: unknown) => void }).setup
  setup({ $adminApi: api, runWithContext: (fn: () => unknown) => fn() })
  register.mock.calls[0]![0](401)
  expect(auth.status).toBe('anonymous')
  expect(useDashboardStore().data).toBeNull()
  expect(useFindingsStore().data).toBeNull()
  expect(navigate).toHaveBeenCalledWith(
    { path: '/login', query: { redirect: '/statistics?period=7d' } },
    { replace: true },
  )
})

it('keeps a rejected post-login session check anonymous', async () => {
  api.session = vi.fn().mockRejectedValue(new AdminApiError(failure(401)))
  const auth = useAuthStore()
  await expect(auth.login('operator', 'synthetic-secret')).rejects.toMatchObject({
    failure: { status: 401 },
  })
  expect(auth.status).toBe('anonymous')
  expect(auth.isAdmin).toBe(false)
})

it('does not let an in-flight 401 add a return target during explicit logout', async () => {
  vi.stubGlobal('defineNuxtPlugin', (plugin: unknown) => plugin)
  const auth = useAuthStore()
  await auth.checkSession()
  vi.stubGlobal('useAuthStore', () => auth)
  vi.stubGlobal('useRouter', () => ({
    currentRoute: { value: { path: '/findings', fullPath: '/findings' } },
  }))
  const register = vi.spyOn(api, 'onAccessLost')
  const { default: plugin } = await import('../../app/plugins/auth')
  ;(plugin as unknown as { setup: (app: unknown) => void }).setup({
    $adminApi: api,
    runWithContext: (fn: () => unknown) => fn(),
  })
  let resolve!: (value: { status: 'ok' }) => void
  api.logout = vi.fn().mockReturnValue(
    new Promise((r) => {
      resolve = r
    }),
  )
  const pending = auth.logout()
  expect(auth.loggingOut).toBe(true)
  register.mock.calls[0]![0](401)
  expect(navigate).not.toHaveBeenCalled()
  resolve({ status: 'ok' })
  await pending
  expect(navigate).toHaveBeenCalledExactlyOnceWith('/login', { replace: true })
  expect(auth.loggingOut).toBe(false)
  expect(auth.status).toBe('anonymous')
})
