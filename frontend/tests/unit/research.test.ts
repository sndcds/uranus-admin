import { describe, expect, it, vi } from 'vitest'
import { researchDetailSchema, researchPageSchema } from '../../shared/contracts'
import { researchQuery, researchUrlQuery } from '../../app/utils/research'
import { researchRelations } from '../../app/utils/research-relations'
import { workspaceTarget } from '../../app/utils/auth-redirect'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'
import { createAdminApi } from '../../app/utils/admin-api'
import { researchDetail, researchPage } from '../fixtures/research'
import { sqlCsv } from '../../app/utils/sql-csv'

describe('research contracts and boundaries', () => {
  it('accepts only safe research response fields, including nested records', () => {
    expect(researchDetailSchema.safeParse(researchDetail()).success).toBe(true)
    for (const field of ['email', 'actor', 'finding_count', 'admin_url', 'sessions']) {
      const detail = researchDetail()
      expect(
        researchDetailSchema.safeParse({ ...detail, item: { ...detail.item, [field]: 'private' } })
          .success,
      ).toBe(false)
    }
    expect(researchPageSchema.safeParse(researchPage()).success).toBe(true)
  })
  it('round-trips filters and rejects ambiguous or unsupported values', () => {
    const filters = {
      q: 'Jazz',
      from_date: '2026-01-01',
      to_date: '2026-06-30',
      city: 'Flensburg',
      category: 2,
      status: 'released' as const,
    }
    expect(researchQuery(researchUrlQuery(filters))).toEqual({ success: true, data: filters })
    for (const query of [
      { status: 'draft' },
      { page_size: '101' },
      { q: ['a', 'b'] },
      { from_date: '2026-12-01', to_date: '2026-01-01' },
      { sql: 'SELECT' },
    ])
      expect(researchQuery(query).success).toBe(false)
  })
  it('keeps journalist return paths in research and preserves admin redirects', () => {
    expect(workspaceTarget('/sql', '', false)).toBe('/research')
    expect(workspaceTarget('/research/events?city=Flensburg', '#timeline', false)).toBe(
      '/research/events?city=Flensburg#timeline',
    )
    expect(workspaceTarget('//evil.invalid', '', false)).toBe('/research')
    expect(workspaceTarget('/findings', '', true)).toBe('/findings')
  })
  it('derives only returned public relations and never administrative targets', () => {
    const graph = researchRelations(researchDetail())
    expect(graph.edges.map((e) => e.type)).toContain('event_date_uses_venue')
    expect(graph.nodes.every((n) => n.admin_url === null && n.type !== 'user')).toBe(true)
    expect(
      graph.edges.every(
        (e) =>
          graph.nodes.some((n) => n.id === e.source) && graph.nodes.some((n) => n.id === e.target),
      ),
    ).toBe(true)
  })
  it('exports spreadsheet text safely', () => {
    expect(sqlCsv(['title'], [{ title: '=HYPERLINK("bad")' }])).toContain("'=HYPERLINK")
  })
  it('uses the existing API client and omits research queries from SQL inspection state', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(researchPage())))
    const api = createAdminApi(fetcher)
    await api.researchSearch({ city: 'Flensburg' })
    expect(fetcher.mock.calls[0]![0]).toContain('/api/admin/api/v1/research/search?city=Flensburg')
    expect(api.viewRead('/api/v1/research/search')).toBeUndefined()
  })
  it.each([
    ['/api/v1/research/search', 'GET', 'q=Jazz', 200],
    ['/api/v1/research/export', 'GET', 'city=Flensburg', 200],
    ['/api/v1/research/events/20000000-0000-4000-8000-000000000001', 'GET', '', 200],
    ['/api/v1/research/users', 'GET', '', 404],
    ['/api/v1/research/search', 'POST', '', 405],
    ['/api/v1/research/search', 'GET', 'q=a&q=b', 422],
    ['/api/v1/research/search', 'GET', 'status=draft', 422],
    ['/api/v1/research/search', 'GET', 'sql=SELECT', 422],
  ])('proxy boundary %s %s %s', async (path, method, query, status) => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{}'))
    const result = await forwardAdminRequest(
      { path, method, query: new URLSearchParams(query), authorization: 'Bearer synthetic' },
      'http://127.0.0.1:9000',
      fetcher,
    )
    expect(result.status).toBe(status)
    expect(fetcher).toHaveBeenCalledTimes(status === 200 ? 1 : 0)
  })
})

describe('experimental semantic search', () => {
  it('preserves semantic URL state and rejects empty, long or ambiguous input', () => {
    const query = { q: 'Wo können Jugendliche kreativ werden?', search_mode: 'semantic' as const }
    expect(researchQuery(researchUrlQuery(query))).toEqual({ success: true, data: query })
    for (const q of ['', ' ', 'x', 'x'.repeat(121)])
      expect(researchQuery({ q, search_mode: 'semantic' }).success).toBe(false)
    expect(researchQuery({ q: 'creative', search_mode: 'unknown' }).success).toBe(false)
  })
  it('calls the semantic endpoint with event filters and no UI mode or model parameter', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(researchPage())))
    await createAdminApi(fetcher).researchSemanticSearch({
      q: 'creative',
      search_mode: 'semantic',
      entity_type: 'all',
      category: 2,
      city: 'Flensburg',
      sort: 'name',
      page: 9,
      page_size: 100,
    })
    const url = new URL(fetcher.mock.calls[0]![0], 'http://localhost')
    expect(url.pathname).toBe('/api/admin/api/v1/research/semantic-search')
    expect(Object.fromEntries(url.searchParams)).toEqual({
      q: 'creative',
      entity_type: 'event',
      category: '2',
      city: 'Flensburg',
      page_size: '20',
    })
  })
  it.each([
    ['GET', 'q=creative', 200],
    ['POST', 'q=creative', 405],
    ['GET', '', 422],
    ['GET', 'q=', 422],
    ['GET', 'q=a&q=b', 422],
    ['GET', 'q=creative&model=jina-v3', 422],
    ['GET', 'q=creative&entity_type=venue', 422],
    ['GET', 'q=creative&page_size=21', 422],
    ['GET', 'q=creative&sort=name', 422],
  ])('semantic proxy boundary %s %s', async (method, query, status) => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(researchPage())))
    const result = await forwardAdminRequest(
      {
        path: '/api/v1/research/semantic-search',
        method,
        query: new URLSearchParams(query),
        authorization: 'Bearer synthetic',
      },
      'http://backend.invalid',
      fetcher,
    )
    expect(result.status).toBe(status)
    if (status !== 200) expect(fetcher).not.toHaveBeenCalled()
  })
})

it('serializes semantic area IDs as repeated query parameters', async () => {
  const areas = ['00000000-0000-4000-8000-000000000991', '00000000-0000-4000-8000-000000000992']
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(researchPage())))
  await createAdminApi(fetcher).researchSemanticSearch({ q: 'creative', area_ids: areas })
  const url = new URL(fetcher.mock.calls[0]![0], 'http://localhost')
  expect(url.searchParams.getAll('area_ids')).toEqual(areas)
})

it.each([
  ['semantic-search', ['00000000-0000-4000-8000-000000000991'], false, 200],
  [
    'semantic-search',
    ['00000000-0000-4000-8000-000000000991', '00000000-0000-4000-8000-000000000992'],
    false,
    200,
  ],
  [
    'semantic-search',
    ['00000000-0000-4000-8000-000000000991', '00000000-0000-4000-8000-000000000991'],
    false,
    200,
  ],
  ['semantic-search', [''], false, 422],
  ['semantic-search', ['bad', '00000000-0000-4000-8000-000000000991'], false, 422],
  [
    'semantic-search',
    Array(51).fill('00000000-0000-4000-8000-000000000991') as string[],
    false,
    422,
  ],
  ['semantic-search', ['00000000-0000-4000-8000-000000000991'], true, 422],
  ['search', ['00000000-0000-4000-8000-000000000991'], false, 422],
])('bounds repeated areas to semantic search: %s %s', async (path, areas, single, status) => {
  const query = new URLSearchParams({ q: 'creative' })
  for (const area of areas) query.append('area_ids', area)
  if (single) query.set('area_id', '00000000-0000-4000-8000-000000000991')
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(researchPage())))
  const result = await forwardAdminRequest(
    { path: `/api/v1/research/${path}`, method: 'GET', query, authorization: 'Bearer synthetic' },
    'http://backend.invalid',
    fetcher,
  )
  expect(result.status).toBe(status)
  if (status === 200) {
    expect(new URL(fetcher.mock.calls[0]![0]).searchParams.getAll('area_ids')).toEqual(areas)
  } else expect(fetcher).not.toHaveBeenCalled()
})

it('rejects an explicit empty area list before it can become an unfiltered request', async () => {
  const fetcher = vi.fn()
  await expect(
    createAdminApi(fetcher).researchSemanticSearch({ q: 'creative', area_ids: [] }),
  ).rejects.toThrow()
  expect(fetcher).not.toHaveBeenCalled()
})

describe('structured semantic genre filters', () => {
  it('serializes and forwards only the allowlisted repeated filters', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(researchPage())))
    const areas = ['00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002']
    await createAdminApi(fetcher).researchSemanticSearch({
      q: 'Live-Musik',
      category: 2,
      genre_keys: ['1:2', '1:3'],
      area_ids: areas,
    })
    const url = new URL(fetcher.mock.calls[0]![0], 'http://localhost')
    expect(url.searchParams.getAll('genre_keys')).toEqual(['1:2', '1:3'])
    expect(url.searchParams.getAll('area_ids')).toEqual(areas)
    const upstream = vi.fn().mockResolvedValue(new Response(JSON.stringify(researchPage())))
    const result = await forwardAdminRequest(
      {
        path: '/api/v1/research/semantic-search',
        method: 'GET',
        query: url.searchParams,
        authorization: 'Bearer synthetic',
      },
      'http://backend.invalid',
      upstream,
    )
    expect(result.status).toBe(200)
    const forwarded = new URL(upstream.mock.calls[0]![0])
    expect(forwarded.searchParams.getAll('genre_keys')).toEqual(['1:2', '1:3'])
    expect(forwarded.searchParams.getAll('area_ids')).toEqual(areas)
    expect(forwarded.searchParams.get('category')).toBe('2')
  })
  it.each([
    'genre_keys=Jazz',
    'genre_keys=1:0',
    'genre_keys=01:2',
    'genre_keys=-0:2',
    'genre_keys=1:2147483648',
    'genre_keys=1:2:3',
    'genre_keys=1:2%0A',
    Array(51).fill('genre_keys=1:2').join('&'),
    'genre_keys=1:2&category=1&category=2',
    'area_ids=not-a-uuid',
    'area_id=00000000-0000-4000-8000-000000000001&area_ids=00000000-0000-4000-8000-000000000002',
  ])('rejects invalid structured queries: %s', async (query) => {
    const fetcher = vi.fn()
    const result = await forwardAdminRequest(
      {
        path: '/api/v1/research/semantic-search',
        method: 'GET',
        query: new URLSearchParams('q=Live-Musik&' + query),
        authorization: 'Bearer synthetic',
      },
      'http://backend.invalid',
      fetcher,
    )
    expect(result.status).toBe(422)
    expect(fetcher).not.toHaveBeenCalled()
  })
  it('keeps repeated genres exclusive to semantic search', async () => {
    const fetcher = vi.fn()
    const result = await forwardAdminRequest(
      {
        path: '/api/v1/research/search',
        method: 'GET',
        query: new URLSearchParams('q=music&genre_keys=1:2'),
        authorization: 'Bearer synthetic',
      },
      'http://backend.invalid',
      fetcher,
    )
    expect(result.status).toBe(422)
    expect(fetcher).not.toHaveBeenCalled()
  })
})
