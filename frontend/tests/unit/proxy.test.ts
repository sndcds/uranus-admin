import { describe, expect, it, vi } from 'vitest'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'

const base = 'http://127.0.0.1:8000'
const input = {
  path: '/api/v1/findings',
  method: 'GET',
  query: new URLSearchParams(),
  authorization: 'Bearer test-credential',
}

describe('bounded admin proxy', () => {
  it.each([
    '/unknown',
    '//evil.invalid',
    '/api/v1/../secret',
    '/api/v1/findings/extra',
    '/__proto__',
  ])('rejects path %s', async (path) => {
    const fetcher = vi.fn()
    expect((await forwardAdminRequest({ ...input, path }, base, fetcher)).status).toBe(404)
    expect(fetcher).not.toHaveBeenCalled()
  })
  it('does not grant access without credentials or accept write methods', async () => {
    const fetcher = vi.fn()
    expect(
      (await forwardAdminRequest({ ...input, authorization: undefined }, base, fetcher)).status,
    ).toBe(401)
    expect((await forwardAdminRequest({ ...input, method: 'POST' }, base, fetcher)).status).toBe(
      405,
    )
    expect(fetcher).not.toHaveBeenCalled()
  })
  it('keeps actual route, encodes queries and sends only authorization', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{"items":[]}'))
    await forwardAdminRequest(
      { ...input, query: new URLSearchParams({ rule: 'a&b', page: '2' }) },
      base,
      fetcher,
    )
    expect(String(fetcher.mock.calls[0]?.[0])).toBe(`${base}/api/v1/findings?rule=a%26b&page=2`)
    expect(fetcher.mock.calls[0]?.[1]).toMatchObject({
      method: 'GET',
      redirect: 'error',
      cache: 'no-store',
      headers: { Accept: 'application/json', Authorization: input.authorization },
    })
  })
  it('rejects arbitrary target parameters, duplicates and credentials in configuration', async () => {
    for (const query of ['url=http://evil.invalid', 'page=1&page=2'])
      expect(
        (await forwardAdminRequest({ ...input, query: new URLSearchParams(query) }, base)).status,
      ).toBe(422)
    expect((await forwardAdminRequest(input, 'http://user:password@localhost/')).status).toBe(503)
  })
  it.each([401, 403, 422, 500, 503])(
    'preserves status %i and sanitizes backend errors',
    async (status) => {
      const result = await forwardAdminRequest(
        input,
        base,
        vi.fn().mockResolvedValue(new Response('private-stacktrace', { status })),
      )
      expect(result.status).toBe(status)
      expect(JSON.stringify(result)).not.toContain('private-stacktrace')
    },
  )
  it('maps timeout and network errors and allows only the configured health route', async () => {
    expect(
      (
        await forwardAdminRequest(
          input,
          base,
          vi.fn().mockRejectedValue(new DOMException('secret', 'TimeoutError')),
        )
      ).status,
    ).toBe(504)
    expect(
      (await forwardAdminRequest(input, base, vi.fn().mockRejectedValue(new Error('secret'))))
        .status,
    ).toBe(502)
    expect(
      (
        await forwardAdminRequest(
          { ...input, path: '/health', authorization: undefined },
          base,
          vi.fn().mockResolvedValue(new Response('{"status":"ok"}')),
        )
      ).status,
    ).toBe(200)
  })
})


it.each([
  [401, 'authentication_required'], [401, 'invalid_credentials'], [403, 'permission_denied'],
  [422, 'invalid_input'], [500, 'internal_error'], [503, 'admin_auth_unconfigured'],
  [503, 'source_timezone_unconfigured'], [503, 'database_unavailable'],
])('preserves validated code %s %s without relaying details', async (status, code) => {
  const result = await forwardAdminRequest(input, base, vi.fn().mockResolvedValue(
    Response.json({ error: { code, message: 'private exception details' } }, { status: Number(status) }),
  ))
  expect(result).toMatchObject({ status, body: { error: { code } } })
  expect(JSON.stringify(result)).not.toContain('private exception')
})

it.each([
  ['{"error":{"code":"unknown","message":"secret"}}', 'application/json'],
  ['{"error":{"code":"database_unavailable","message":"secret","traceback":"secret"}}', 'application/json'],
  ['{bad json', 'application/json'], ['<html>secret</html>', 'text/html'],
  ['secret', 'text/plain'],
  ['{"error":{"code":"invalid_credentials","message":"secret"}}', 'application/json'],
])('sanitizes untrusted errors %s', async (body, type) => {
  const result = await forwardAdminRequest(input, base, vi.fn().mockResolvedValue(
    new Response(body, { status: 503, headers: { 'Content-Type': type } }),
  ))
  expect(result).toMatchObject({ status: 503, body: { error: { code: 'upstream_error' } } })
  expect(JSON.stringify(result)).not.toContain('secret')
})
