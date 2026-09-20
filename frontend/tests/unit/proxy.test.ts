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
  [401, 'authentication_required'],
  [401, 'invalid_credentials'],
  [403, 'permission_denied'],
  [422, 'invalid_input'],
  [500, 'internal_error'],
  [503, 'admin_auth_unconfigured'],
  [503, 'source_timezone_unconfigured'],
  [503, 'database_unavailable'],
])('preserves validated code %s %s without relaying details', async (status, code) => {
  const result = await forwardAdminRequest(
    input,
    base,
    vi
      .fn()
      .mockResolvedValue(
        Response.json(
          { error: { code, message: 'private exception details' } },
          { status: Number(status) },
        ),
      ),
  )
  expect(result).toMatchObject({ status, body: { error: { code } } })
  expect(JSON.stringify(result)).not.toContain('private exception')
})

it.each([
  ['{"error":{"code":"unknown","message":"secret"}}', 'application/json'],
  [
    '{"error":{"code":"database_unavailable","message":"secret","traceback":"secret"}}',
    'application/json',
  ],
  ['{bad json', 'application/json'],
  ['<html>secret</html>', 'text/html'],
  ['secret', 'text/plain'],
  ['{"error":{"code":"invalid_credentials","message":"secret"}}', 'application/json'],
])('sanitizes untrusted errors %s', async (body, type) => {
  const result = await forwardAdminRequest(
    input,
    base,
    vi
      .fn()
      .mockResolvedValue(new Response(body, { status: 503, headers: { 'Content-Type': type } })),
  )
  expect(result).toMatchObject({ status: 503, body: { error: { code: 'upstream_error' } } })
  expect(JSON.stringify(result)).not.toContain('secret')
})

it('allows only validated admin review and check mutations', async () => {
  const fetcher = vi.fn().mockImplementation(async () => Response.json({ status: 'success' }))
  const review = {
    finding_id: 'rule:venue:key:field',
    status: 'exception',
    exception_reason: 'Agreed',
  }
  expect(
    (
      await forwardAdminRequest(
        { ...input, path: '/api/v1/finding-reviews', method: 'PATCH', body: review },
        base,
        fetcher,
      )
    ).status,
  ).toBe(200)
  expect(fetcher.mock.calls[0]?.[1]).toMatchObject({
    method: 'PATCH',
    body: JSON.stringify(review),
  })
  expect(
    (
      await forwardAdminRequest(
        {
          ...input,
          path: '/api/v1/finding-reviews',
          method: 'PATCH',
          body: { ...review, status: 'resolved' },
        },
        base,
        fetcher,
      )
    ).status,
  ).toBe(422)
  expect(
    (
      await forwardAdminRequest(
        {
          ...input,
          path: '/api/v1/finding-reviews',
          method: 'PATCH',
          body: { ...review, sql: 'UPDATE uranus.venue' },
        },
        base,
        fetcher,
      )
    ).status,
  ).toBe(422)
  expect(
    (
      await forwardAdminRequest(
        { ...input, path: '/api/v1/check-runs', method: 'POST', body: {} },
        base,
        fetcher,
      )
    ).status,
  ).toBe(200)
  expect(
    (
      await forwardAdminRequest(
        {
          ...input,
          path: '/api/v1/check-runs',
          method: 'POST',
          body: { organization_id: 'guess' },
        },
        base,
        fetcher,
      )
    ).status,
  ).toBe(422)
  expect(fetcher).toHaveBeenCalledTimes(2)
})

it.each([
  '/api/v1/record-marks/not-a-uuid',
  '/api/v1/record-marks/00000000-0000-0000-0000-000000000020/extra',
  '/api/v1/record-marks/00000000-0000-0000-0000-000000000020%2fextra',
  '/api/v1/record-marks/../../health',
])('rejects malformed mark detail path %s', async (path) => {
  const fetcher = vi.fn()
  expect((await forwardAdminRequest({ ...input, path }, base, fetcher)).status).toBe(404)
  expect(fetcher).not.toHaveBeenCalled()
})

it('forwards only explicit authorization and omits ambient credentials', async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json({ items: [] }))
  await forwardAdminRequest(
    { ...input, headers: { Cookie: 'secret', 'X-Admin': 'true' } } as typeof input,
    base,
    fetcher,
  )
  expect(fetcher.mock.calls[0]?.[1].headers).toEqual({
    Accept: 'application/json',
    Authorization: input.authorization,
  })
  expect(fetcher.mock.calls[0]?.[1].credentials).toBe('omit')
})

it('allows only GET on strict check job UUID detail paths', async () => {
  const fetcher = vi.fn().mockImplementation(async () => new Response('{}'))
  const path = '/api/v1/check-runs/10000000-0000-4000-8000-000000000001'
  expect((await forwardAdminRequest({ ...input, path }, base, fetcher)).status).toBe(200)
  expect(
    (await forwardAdminRequest({ ...input, path, method: 'POST' }, base, fetcher)).status,
  ).toBe(405)
  expect(
    (await forwardAdminRequest({ ...input, path: '/api/v1/check-runs/not-a-uuid' }, base, fetcher))
      .status,
  ).toBe(404)
})

it.each(['events', 'venues', 'spaces', 'organizations', 'users', 'images'])(
  'allows only explicit read-only %s routes',
  async (section) => {
    const fetcher = vi.fn().mockImplementation(async () => new Response('{}'))
    for (const suffix of ['', '/00000000-0000-4000-8000-000000000001']) {
      expect(
        (
          await forwardAdminRequest(
            { ...input, path: `/api/v1/${section}${suffix}` },
            base,
            fetcher,
          )
        ).status,
      ).toBe(200)
      expect(
        (
          await forwardAdminRequest(
            { ...input, path: `/api/v1/${section}${suffix}`, method: 'POST' },
            base,
            fetcher,
          )
        ).status,
      ).toBe(405)
    }
    expect(
      (await forwardAdminRequest({ ...input, path: `/api/v1/${section}/bad` }, base, fetcher))
        .status,
    ).toBe(404)
  },
)

it('allows authenticated read-only entity search with only its declared filters', async () => {
  const request = {
    ...input,
    path: '/api/v1/entity-search',
    query: new URLSearchParams({
      q: '100%_\\',
      entity_type: 'user',
      organization_id: 'org',
      status: 'active',
      limit: '20',
    }),
  }
  const fetcher = vi.fn().mockResolvedValue(new Response('{"items":[]}'))
  expect((await forwardAdminRequest(request, base, fetcher)).status).toBe(200)
  const url = new URL(String(fetcher.mock.calls[0]?.[0]))
  expect(url.searchParams.get('q')).toBe('100%_\\')
  expect(url.pathname).toBe('/api/v1/entity-search')
  expect(
    (await forwardAdminRequest({ ...request, authorization: undefined }, base, fetcher)).status,
  ).toBe(401)
  expect((await forwardAdminRequest({ ...request, method: 'POST' }, base, fetcher)).status).toBe(
    405,
  )
  expect(
    (
      await forwardAdminRequest(
        { ...request, query: new URLSearchParams('q=max&token=secret') },
        base,
        fetcher,
      )
    ).status,
  ).toBe(422)
  expect(fetcher).toHaveBeenCalledTimes(1)
})

it.each([
  '/api/v1/events',
  '/api/v1/organizations',
  '/api/v1/venues',
  '/api/v1/spaces',
  '/api/v1/entity-search',
])('forwards temporal and existing organization filters for %s', async (path) => {
  const fetcher = vi.fn().mockResolvedValue(new Response('{"items":[]}'))
  const query = new URLSearchParams({
    temporal: 'upcoming',
    period: '7d',
    organization_id: 'org',
    q: 'hacks',
  })
  expect((await forwardAdminRequest({ ...input, path, query }, base, fetcher)).status).toBe(200)
  const url = new URL(String(fetcher.mock.calls[0]?.[0]))
  expect(url.searchParams.get('temporal')).toBe('upcoming')
  expect(url.searchParams.get('period')).toBe('7d')
  expect(url.searchParams.get('organization_id')).toBe('org')
})

it.each(['events', 'users', 'organizations', 'venues', 'spaces', 'images', 'entity-search'])(
  'forwards created period on %s without weakening the query allowlist',
  async (section) => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({ items: [] }))
    const request = {
      ...input,
      path: `/api/v1/${section}`,
      query: new URLSearchParams({ period: '90d', q: 'max' }),
    }
    expect((await forwardAdminRequest(request, base, fetcher)).status).toBe(200)
    const url = new URL(String(fetcher.mock.calls[0]?.[0]))
    expect(Object.fromEntries(url.searchParams)).toEqual({ period: '90d', q: 'max' })
    request.query.append('period', '7d')
    expect((await forwardAdminRequest(request, base, fetcher)).status).toBe(422)
    expect(fetcher).toHaveBeenCalledTimes(1)
  },
)

it('forwards active_only only on findings and rejects duplicate filter keys', async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response('{}'))
  const query = new URLSearchParams('active_only=true&severity=error')
  await forwardAdminRequest({ ...input, query }, base, fetcher)
  expect(String(fetcher.mock.calls[0]?.[0])).toBe(`${base}/api/v1/findings?${query}`)
  fetcher.mockClear()
  query.append('active_only', 'false')
  expect((await forwardAdminRequest({ ...input, query }, base, fetcher)).status).toBe(422)
  expect(fetcher).not.toHaveBeenCalled()
  expect(
    (
      await forwardAdminRequest(
        { ...input, path: '/api/v1/check-runs', query: new URLSearchParams('active_only=true') },
        base,
        fetcher,
      )
    ).status,
  ).toBe(422)
})
