import { describe, expect, it, vi } from 'vitest'
import { markCreateSchema, markUpdateSchema } from '../../shared/contracts'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'

const id = '10000000-0000-4000-8000-000000000020'
const create = { entity_type: 'venue', entity_key: id, reasons: ['incorrect'], urgency: 'normal' }
const update = {
  version: 1,
  status: 'done',
  reasons: ['incorrect'],
  urgency: 'normal',
  note: 'Korrigiert',
}
const base = 'http://127.0.0.1:8000'
const input = {
  path: '/api/v1/record-marks',
  method: 'POST',
  body: create,
  authorization: 'Bearer fixture-token',
  query: new URLSearchParams(),
}

describe('record mark contracts and proxy', () => {
  it('requires known reasons, explains other, and forbids author or timestamp forgery', () => {
    expect(markCreateSchema.safeParse(create).success).toBe(true)
    expect(markUpdateSchema.safeParse(update).success).toBe(true)
    for (const extra of [
      { reasons: [] },
      { reasons: ['invented'] },
      { reasons: ['incorrect', 'incorrect'] },
      { reasons: ['other'], reason_detail: ' ' },
      { created_by: 'fake' },
      { note: ' ' },
    ])
      expect(markCreateSchema.safeParse({ ...create, ...extra }).success).toBe(false)
    expect(
      markCreateSchema.safeParse({ ...create, reasons: ['other'], reason_detail: 'Prüfen' })
        .success,
    ).toBe(true)
    for (const extra of [
      { completed_by: 'fake' },
      { completed_at: '2026-09-14T12:00:00Z' },
      { version: 0 },
    ])
      expect(markUpdateSchema.safeParse({ ...update, ...extra }).success).toBe(false)
  })
  it('forwards only authenticated, validated mark writes and bounded paths', async () => {
    const fetcher = vi.fn().mockImplementation(async () => new Response('{}', { status: 201 }))
    expect((await forwardAdminRequest(input, base, fetcher)).status).toBe(201)
    expect(fetcher.mock.calls[0]?.[1]).toMatchObject({
      method: 'POST',
    })
    expect(JSON.parse(fetcher.mock.calls[0]?.[1].body)).toEqual(create)
    fetcher.mockClear()
    for (const variant of [
      { ...input, authorization: undefined },
      { ...input, body: { ...create, created_by: 'forged' } },
      { ...input, method: 'DELETE' },
      { ...input, path: '/api/v1/record-marks/not-a-uuid', method: 'PATCH', body: update },
      { ...input, query: new URLSearchParams('status=done') },
    ])
      expect((await forwardAdminRequest(variant, base, fetcher)).status).toBeGreaterThanOrEqual(400)
    expect(fetcher).not.toHaveBeenCalled()
    const result = await forwardAdminRequest(
      { ...input, path: `${input.path}/${id}`, method: 'PATCH', body: update },
      base,
      fetcher,
    )
    expect(result.status).toBe(201)
  })
  it('retains conflict status and accepts filters on the mark list', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'mark_conflict', message: 'Changed' } }), {
        status: 409,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const result = await forwardAdminRequest(
      { ...input, path: `${input.path}/${id}`, method: 'PATCH', body: update },
      base,
      fetcher,
    )
    expect(result).toMatchObject({ status: 409, body: { error: { code: 'mark_conflict' } } })
    const listFetcher = vi.fn().mockResolvedValue(new Response('{}'))
    expect(
      (
        await forwardAdminRequest(
          {
            ...input,
            method: 'GET',
            query: new URLSearchParams('status=done&reason=incorrect&sort=urgency'),
          },
          base,
          listFetcher,
        )
      ).status,
    ).toBe(200)
  })
})
