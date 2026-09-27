import { describe, expect, it, vi } from 'vitest'
import { researchAreaDossierSchema, researchAreasSchema } from '../../shared/research'
import { researchQuery, researchUrlQuery } from '../../app/utils/research'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'
import { createAdminApi } from '../../app/utils/admin-api'
import { researchArea, researchAreaDossier } from '../fixtures/research'

describe('municipality research', () => {
  it('validates list and boundary dossiers without private fields', () => {
    expect(researchAreaDossierSchema.safeParse(researchAreaDossier()).success).toBe(true)
    expect(
      researchAreaDossierSchema.safeParse({
        ...researchAreaDossier(),
        geometry: { type: 'Point', coordinates: [9, 54] },
      }).success,
    ).toBe(false)
    const list = {
      items: [researchArea],
      pagination: { page: 1, page_size: 10, pages: 1, total: 1 },
    }
    expect(researchAreasSchema.safeParse(list).success).toBe(true)
    expect(
      researchAreasSchema.safeParse({ ...list, items: [{ ...researchArea, geometry: {} }] })
        .success,
    ).toBe(false)
  })
  it('retains area with city and occurrence filters in permalinks', () => {
    const query = {
      area_id: researchArea.id,
      city: 'Flensburg',
      category: 1,
      from_date: '2026-09-01',
    }
    expect(researchQuery(researchUrlQuery(query))).toEqual({ success: true, data: query })
    expect(researchQuery({ area_id: 'R27020' }).success).toBe(false)
  })
  it('passes the identical area filter to CSV export', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ columns: [], rows: [], total: 0, observed_at: '2026-09-27T10:00:00Z' }),
        ),
      )
    await createAdminApi(fetcher).researchExport({ area_id: researchArea.id, city: 'Flensburg' })
    expect(fetcher.mock.calls[0]![0]).toContain(`area_id=${researchArea.id}`)
  })
  it.each([
    ['/api/v1/research/areas', 'GET', 'q=Fl&country_code=DE', 200],
    [`/api/v1/research/areas/${researchArea.id}`, 'GET', 'category=1', 200],
    ['/api/v1/research/search', 'GET', `area_id=${researchArea.id}`, 200],
    ['/api/v1/research/export', 'GET', `area_id=${researchArea.id}`, 200],
    ['/api/v1/research/areas', 'POST', '', 405],
    [`/api/v1/research/areas/${researchArea.id}`, 'PATCH', '', 405],
    ['/api/v1/research/areas/import', 'POST', '', 404],
    ['/api/v1/research/areas', 'GET', 'country_code=FR', 422],
    ['/api/v1/research/areas', 'GET', 'page_size=51', 422],
    ['/api/v1/research/areas', 'GET', 'q=a&q=b', 422],
    ['/api/v1/research/search', 'GET', 'area_id=invalid', 422],
    ['/api/v1/research/areas', 'GET', 'geometry=true', 422],
  ])('bounded read proxy %s %s %s', async (path, method, query, status) => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{}'))
    const result = await forwardAdminRequest(
      { path, method, query: new URLSearchParams(query), authorization: 'Bearer fixture' },
      'http://127.0.0.1:9000',
      fetcher,
    )
    expect(result.status).toBe(status)
    expect(fetcher).toHaveBeenCalledTimes(status === 200 ? 1 : 0)
  })
})
