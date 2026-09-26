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
