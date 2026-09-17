import { afterEach, expect, it, vi } from 'vitest'
import { createAdminApi } from '../../app/utils/admin-api'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'

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
