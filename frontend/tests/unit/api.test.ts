import { describe, expect, it, vi } from 'vitest'
import { filtersSchema } from '../../shared/contracts'
import { createAdminApi } from '../../app/utils/admin-api'
import { summary, findings } from '../fixtures/api'

describe('browser API client', () => {
  it('parses JSON null for an unassigned workflow', async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response('null', {
        status: 200,
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
      }),
    )
    const workflowKey = '00000000-0000-4000-8000-000000000850'
    await expect(
      createAdminApi(fetcher).assignmentForWorkflow('geocode_request', workflowKey),
    ).resolves.toBeNull()
    expect(fetcher.mock.calls[0]?.[0]).toBe(
      `/api/admin/api/v1/assignments?workflow_type=geocode_request&workflow_key=${workflowKey}`,
    )
  })

  it.each([401, 403, 422, 500, 503])(
    'handles HTTP %i without exposing backend text',
    async (status) => {
      const client = createAdminApi(
        vi.fn().mockResolvedValue(
          new Response(JSON.stringify({ error: { code: 'failure', message: 'private-token' } }), {
            status,
          }),
        ),
      )
      await expect(client.summary('24h')).rejects.toMatchObject({ failure: { status } })
      await expect(client.summary('24h')).rejects.not.toThrow('private-token')
    },
  )
  it('sends only the caller-provided credential and never persists it', async () => {
    const fetcher = vi.fn().mockImplementation(async () => new Response(JSON.stringify(summary)))
    const client = createAdminApi(fetcher)
    await client.summary('today')
    expect(fetcher.mock.calls[0]?.[0]).toBe('/api/admin/api/v1/dashboard/summary?period=today')
    expect(fetcher.mock.calls[0]?.[1].headers).toEqual({})
    client.setCredential('explicit-test-credential')
    await client.summary('7d')
    expect(fetcher.mock.calls[1]?.[1].headers.Authorization).toBe('Bearer explicit-test-credential')
    client.clearCredential()
    await client.summary('24h')
    expect(fetcher.mock.calls[2]?.[1].headers).toEqual({})
    expect(JSON.stringify(client)).not.toContain('explicit-test-credential')
  })
  it('rejects malformed success responses and network failures', async () => {
    await expect(
      createAdminApi(vi.fn().mockResolvedValue(new Response('{}'))).summary('24h'),
    ).rejects.toMatchObject({ failure: { code: 'invalid_response' } })
    await expect(
      createAdminApi(vi.fn().mockRejectedValue(new Error('secret'))).summary('24h'),
    ).rejects.toMatchObject({ failure: { status: 502 } })
  })
})

it('serializes active-only findings queries as explicit booleans', async () => {
  const fetcher = vi.fn().mockImplementation(async () => new Response(JSON.stringify(findings)))
  const api = createAdminApi(fetcher)
  for (const active_only of [true, false]) {
    await api.findings(filtersSchema.parse({ active_only }))
    const url = new URL(String(fetcher.mock.lastCall?.[0]), 'http://localhost')
    expect(url.searchParams.get('active_only')).toBe(String(active_only))
  }
})
