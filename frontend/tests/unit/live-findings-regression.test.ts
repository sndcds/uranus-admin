import { afterEach, expect, it, vi } from 'vitest'
import { findingPageSchema, filtersSchema } from '../../shared/contracts'
import { createAdminApi } from '../../app/utils/admin-api'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'
import { liveFindings } from '../fixtures/live-findings'

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

function controlledTimers() {
  vi.useFakeTimers()
  // Native AbortSignal.timeout uses runtime timers, not Vitest's fake clock.
  return vi.spyOn(AbortSignal, 'timeout').mockImplementation((ms) => {
    const controller = new AbortController()
    setTimeout(() => controller.abort(new DOMException('Timeout', 'TimeoutError')), ms)
    return controller.signal
  })
}

function delayedFetch(delay: number) {
  return vi.fn(
    (_path: string | URL, options: RequestInit) =>
      new Promise<Response>((resolve, reject) => {
        const timer = setTimeout(() => resolve(Response.json(liveFindings)), delay)
        options.signal?.addEventListener(
          'abort',
          () => {
            clearTimeout(timer)
            reject(options.signal?.reason)
          },
          { once: true },
        )
      }),
  )
}

it('accepts all reported live response shapes', () => {
  const parsed = findingPageSchema.safeParse(liveFindings)
  expect(parsed.success).toBe(true)
  if (!parsed.success) return
  expect(parsed.data.items).toHaveLength(50)
  expect(parsed.data.items[0]?.metadata).toEqual({
    source_fingerprint: 'a'.repeat(64),
    category: 'integrity',
  })
  expect(parsed.data.pagination).toEqual({ page: 1, page_size: 50, total: 932, pages: 19 })
  expect(parsed.data.cursor_pagination).toBeNull()
  expect(parsed.data.items[1]).toMatchObject({
    entity_type: 'image_link',
    entity_id: null,
    action: null,
    image_url: null,
  })
})

it('live findings survive 13 seconds in the browser client', async () => {
  const timeout = controlledTimers()
  const result = createAdminApi(delayedFetch(13_000)).findings(
    filtersSchema.parse({ mode: 'live' }),
  )
  await Promise.all([
    expect(result).resolves.toMatchObject({ mode: 'live' }),
    vi.advanceTimersByTimeAsync(13_000),
  ])
  expect(timeout).toHaveBeenCalledWith(60_000)
})

it('live findings survive 13 seconds through the Nitro proxy', async () => {
  controlledTimers()
  const result = forwardAdminRequest(
    {
      path: '/api/v1/findings',
      method: 'GET',
      query: new URLSearchParams('mode=live'),
      authorization: 'Bearer synthetic',
    },
    'http://127.0.0.1:8000',
    delayedFetch(13_000),
  )
  await vi.advanceTimersByTimeAsync(13_000)
  expect(await result).toMatchObject({ status: 200, body: { mode: 'live' } })
})

it.each(['session', 'summary', 'entities', 'entity', 'search', 'persisted', 'default'] as const)(
  '%s keeps the 12 second browser deadline',
  async (kind) => {
    const timeout = controlledTimers()
    const client = createAdminApi(delayedFetch(13_000))
    const result =
      kind === 'session'
        ? client.session()
        : kind === 'summary'
          ? client.summary('24h')
          : kind === 'entities'
            ? client.entities('events', { page: 1 })
            : kind === 'entity'
              ? client.entity('events', '00000000-0000-4000-8000-000000000030')
              : kind === 'search'
                ? client.globalSearch({ q: 'test' })
                : client.findings(
                    filtersSchema.parse(kind === 'persisted' ? { mode: 'persisted' } : {}),
                  )
    await Promise.all([
      expect(result).rejects.toMatchObject({ failure: { status: 504, code: 'request_timeout' } }),
      vi.advanceTimersByTimeAsync(12_000),
    ])
    expect(timeout).toHaveBeenCalledWith(12_000)
  },
)

it('bounds live findings at 60 seconds with a safe specific failure', async () => {
  controlledTimers()
  const result = createAdminApi(delayedFetch(61_000)).findings(
    filtersSchema.parse({ mode: 'live' }),
  )
  await Promise.all([
    expect(result).rejects.toMatchObject({
      failure: { status: 504, code: 'live_findings_timeout' },
    }),
    vi.advanceTimersByTimeAsync(60_000),
  ])
})

it.each([false, true])(
  'preserves caller cancellation (already aborted: %s)',
  async (alreadyAborted) => {
    controlledTimers()
    const controller = new AbortController()
    const reason = new DOMException('Caller cancellation', 'AbortError')
    if (alreadyAborted) controller.abort(reason)
    const fetcher = delayedFetch(61_000)
    const result = createAdminApi((path, options) => {
      options.signal?.throwIfAborted()
      return fetcher(path, options)
    }).findings(filtersSchema.parse({ mode: 'live' }), controller.signal)
    if (!alreadyAborted) controller.abort(reason)
    await expect(result).rejects.toBe(reason)
  },
)

it('the live deadline still applies with an external non-aborted signal', async () => {
  controlledTimers()
  const controller = new AbortController()
  const result = createAdminApi(delayedFetch(61_000)).findings(
    filtersSchema.parse({ mode: 'live' }),
    controller.signal,
  )
  await Promise.all([
    expect(result).rejects.toMatchObject({ failure: { code: 'live_findings_timeout' } }),
    vi.advanceTimersByTimeAsync(60_000),
  ])
  expect(controller.signal.aborted).toBe(false)
})

it('classifies a timeout while reading the body as a timeout', async () => {
  controlledTimers()
  const result = createAdminApi(async (_path, options) => {
    const response = Response.json(liveFindings)
    vi.spyOn(response, 'json').mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          options.signal?.addEventListener('abort', () => reject(options.signal?.reason), {
            once: true,
          })
        }),
    )
    return response
  }).findings(filtersSchema.parse({ mode: 'live' }))
  await Promise.all([
    expect(result).rejects.toMatchObject({ failure: { code: 'live_findings_timeout' } }),
    vi.advanceTimersByTimeAsync(60_000),
  ])
})

it.each(['fetch', 'body'])(
  'reports %s transport failures without exposing exception text',
  async (stage) => {
    const result = createAdminApi(async () => {
      if (stage === 'fetch') throw new TypeError('private detail')
      const response = Response.json(liveFindings)
      vi.spyOn(response, 'json').mockRejectedValue(new TypeError('private detail'))
      return response
    }).findings(filtersSchema.parse({ mode: 'live' }))
    await expect(result).rejects.toMatchObject({ failure: { status: 502, code: 'network_error' } })
    await expect(result).rejects.not.toThrow('private detail')
  },
)

it.each(['{broken json', '{}'])(
  'reports invalid JSON or a schema mismatch as invalid_response: %s',
  async (body) => {
    await expect(
      createAdminApi(async () => new Response(body)).findings(
        filtersSchema.parse({ mode: 'live' }),
      ),
    ).rejects.toMatchObject({ failure: { status: 502, code: 'invalid_response' } })
  },
)

it('metadata preserves rule-dependent JSON and rejects non-JSON values', () => {
  const page = structuredClone(liveFindings)
  const metadata = { nested: { unknown: [1, true, null, 'reason'] } }
  expect(
    findingPageSchema.parse({ ...page, items: [{ ...page.items[0], metadata }] }).items[0]
      ?.metadata,
  ).toEqual(metadata)
  for (const invalid of [null, [], { value: () => 'secret' }, { value: Infinity }]) {
    expect(
      findingPageSchema.safeParse({ ...page, items: [{ ...page.items[0], metadata: invalid }] })
        .success,
    ).toBe(false)
  }
})

it.each([
  ['/api/v1/findings', 'mode=persisted', 10_000],
  ['/api/v1/findings', '', 10_000],
  ['/auth/session', '', 10_000],
  ['/api/v1/events', '', 10_000],
  ['/api/v1/dashboard/summary', '', 10_000],
  ['/api/v1/search', 'q=test', 10_000],
  ['/api/v1/findings', 'mode=live', 58_000],
] as const)('proxy deadline for %s?%s is %i ms', async (path, query, deadline) => {
  const timeout = controlledTimers()
  const result = forwardAdminRequest(
    { path, query: new URLSearchParams(query), method: 'GET', authorization: 'Bearer synthetic' },
    'http://127.0.0.1:8000',
    delayedFetch(61_000),
  )
  await vi.advanceTimersByTimeAsync(deadline)
  expect(await result).toMatchObject({
    status: 504,
    body: { error: { code: deadline === 58_000 ? 'live_findings_timeout' : 'request_timeout' } },
  })
  expect(timeout).toHaveBeenCalledWith(deadline)
})

it('the proxy separates malformed success JSON from transport failures', async () => {
  const input = {
    path: '/api/v1/findings',
    query: new URLSearchParams('mode=live'),
    method: 'GET',
    authorization: 'Bearer synthetic',
  }
  for (const [fetcher, code] of [
    [vi.fn().mockResolvedValue(new Response('{private malformed content')), 'invalid_response'],
    [vi.fn().mockRejectedValue(new TypeError('private detail')), 'network_error'],
  ] as const) {
    const result = await forwardAdminRequest(input, 'http://127.0.0.1:8000', fetcher)
    expect(result).toMatchObject({ status: 502, body: { error: { code } } })
    expect(JSON.stringify(result)).not.toContain('private')
  }
})

it('the proxy recognizes its deadline when body consumption rejects with AbortError', async () => {
  controlledTimers()
  const result = forwardAdminRequest(
    {
      path: '/api/v1/findings',
      query: new URLSearchParams('mode=live'),
      method: 'GET',
      authorization: 'Bearer synthetic',
    },
    'http://127.0.0.1:8000',
    async (_path, options) => {
      const response = Response.json(liveFindings)
      vi.spyOn(response, 'json').mockImplementation(
        () =>
          new Promise((_resolve, reject) => {
            options.signal?.addEventListener(
              'abort',
              () => reject(new DOMException('Aborted body', 'AbortError')),
              { once: true },
            )
          }),
      )
      return response
    },
  )
  await vi.advanceTimersByTimeAsync(58_000)
  expect(await result).toMatchObject({
    status: 504,
    body: { error: { code: 'live_findings_timeout' } },
  })
})
