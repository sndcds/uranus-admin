import { afterEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import LoginPanel from '../../app/components/LoginPanel.vue'
import { createAdminApi } from '../../app/utils/admin-api'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'
import { AdminApiError, failure } from '../../shared/errors'

const principal = { subject: 'admin:00000000-0000-4000-8000-000000000810', system_admin: true }
const sessionToken = 'S'.repeat(43)
afterEach(() => vi.unstubAllGlobals())

it('uses same-origin HttpOnly sessions and CSRF headers without exposing a credential', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(principal)))
  const api = createAdminApi(fetcher)
  expect(await api.login('operator', 'synthetic-password')).toEqual(principal)
  expect(fetcher.mock.calls[0]?.[0]).toBe('/api/admin/auth/login')
  expect(fetcher.mock.calls[0]?.[1]).toMatchObject({
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-Admin-CSRF': '1' },
  })
  expect(fetcher.mock.calls[0]?.[1].headers.Authorization).toBeUndefined()
  expect(JSON.stringify(api)).not.toContain('synthetic-password')
})

it('forwards only the explicit session cookie and origin/CSRF headers', async () => {
  const fetcher = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(principal), {
      headers: {
        'Set-Cookie': `__Host-admin_session=${sessionToken}; Path=/; Secure; HttpOnly; SameSite=Strict`,
      },
    }),
  )
  const result = await forwardAdminRequest(
    {
      path: '/auth/session',
      method: 'GET',
      query: new URLSearchParams(),
      sessionCookie: `__Host-admin_session=${sessionToken}`,
      origin: 'https://admin.example.test',
      csrf: '1',
    },
    'http://backend:8000',
    fetcher,
  )
  expect(fetcher.mock.calls[0]?.[1]).toMatchObject({
    credentials: 'omit',
    redirect: 'error',
    cache: 'no-store',
    headers: {
      Cookie: `__Host-admin_session=${sessionToken}`,
      Origin: 'https://admin.example.test',
      'X-Admin-CSRF': '1',
    },
  })
  expect(result.body).toEqual(principal)
  expect(JSON.stringify(result.body)).not.toContain(sessionToken)
  expect(
    (
      await forwardAdminRequest(
        {
          path: '/auth/session',
          method: 'GET',
          query: new URLSearchParams(),
          sessionCookie: `admin_session=${sessionToken}; other=secret`,
        },
        'http://backend:8000',
        fetcher,
      )
    ).status,
  ).toBe(401)
})

it.each([401, 403, 429, 503])('sanitizes authentication failure %i', async (status) => {
  const result = await forwardAdminRequest(
    {
      path: '/auth/login',
      method: 'POST',
      query: new URLSearchParams(),
      body: { login: 'operator', password: 'test-password' },
    },
    'http://backend:8000',
    vi.fn().mockResolvedValue(new Response('secret-token', { status })),
  )
  expect(result.status).toBe(status)
  expect(JSON.stringify(result)).not.toContain('secret-token')
})

it('rejects an auth response that accidentally includes tokens', async () => {
  const result = await forwardAdminRequest(
    { path: '/auth/session', method: 'GET', query: new URLSearchParams() },
    'http://backend:8000',
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ ...principal, access_token: sessionToken })),
      ),
  )
  expect(result.status).toBe(503)
  expect(JSON.stringify(result)).not.toContain(sessionToken)
})

it('provides accessible login, clears passwords, retries after login and logs out', async () => {
  const api = {
    session: vi.fn().mockRejectedValue(new AdminApiError(failure(401))),
    login: vi.fn().mockResolvedValue(principal),
    logout: vi.fn().mockResolvedValue({ status: 'ok' }),
    clearCredential: vi.fn(),
  }
  const revision = ref(0)
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
  vi.stubGlobal('useState', () => revision)
  const wrapper = mount(LoginPanel)
  await flushPromises()
  expect(wrapper.get('label[for="admin-password"]').text()).toBe('Passwort')
  await wrapper.get('#admin-login').setValue('operator')
  await wrapper.get('#admin-password').setValue('test-private-password')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.text()).toContain('Als System-Administrator angemeldet')
  expect(wrapper.html()).not.toContain('test-private-password')
  expect(wrapper.emitted('changed')).toHaveLength(1)
  await wrapper.get('button').trigger('click')
  await flushPromises()
  expect(api.logout).toHaveBeenCalledOnce()
  expect(wrapper.get<HTMLInputElement>('#admin-password').element.value).toBe('')
  expect(wrapper.emitted('changed')).toHaveLength(2)
})

it('reports denied global access and returns to login after session loss', async () => {
  const revision = ref(0)
  vi.stubGlobal('useNuxtApp', () => ({
    $adminApi: { session: vi.fn().mockResolvedValue({ ...principal, system_admin: false }) },
  }))
  vi.stubGlobal('useState', () => revision)
  const wrapper = mount(LoginPanel)
  await flushPromises()
  expect(wrapper.text()).toContain('Keine System-Admin-Berechtigung')
  revision.value = 401
  await flushPromises()
  expect(wrapper.find('form').exists()).toBe(true)
})

it('does not let an old denied request invalidate a newly established session', async () => {
  let finishOldRequest!: (response: Response) => void
  const oldResponse = new Promise<Response>((resolve) => {
    finishOldRequest = resolve
  })
  const fetcher = vi
    .fn()
    .mockReturnValueOnce(oldResponse)
    .mockResolvedValueOnce(new Response(JSON.stringify(principal)))
  const api = createAdminApi(fetcher)
  const lost = vi.fn()
  api.onAccessLost(lost)
  const oldRequest = api.summary('24h').catch(() => undefined)
  await api.login('operator', 'synthetic-password')
  finishOldRequest(new Response('{}', { status: 401 }))
  await oldRequest
  expect(lost).not.toHaveBeenCalled()
})

it('keeps logout available and reports an infrastructure failure without claiming success', async () => {
  const api = {
    session: vi.fn().mockResolvedValue(principal),
    logout: vi.fn().mockRejectedValue(new AdminApiError(failure(503))),
    clearCredential: vi.fn(),
  }
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
  vi.stubGlobal('useState', () => ref(0))
  const wrapper = mount(LoginPanel)
  await flushPromises()
  await wrapper.get('button').trigger('click')
  await flushPromises()
  expect(wrapper.get('button').text()).toBe('Abmelden')
  expect(wrapper.text()).not.toContain('Abgemeldet.')
  expect(wrapper.emitted('changed')).toBeUndefined()
  expect(api.clearCredential).not.toHaveBeenCalled()
})
