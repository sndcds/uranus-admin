import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useDashboardStore } from '../../app/stores/dashboard'
import { useFindingsStore } from '../../app/stores/findings'
import { createAdminApi } from '../../app/utils/admin-api'
import type { DashboardSummary } from '../../shared/contracts'
import { AdminApiError, failure } from '../../shared/errors'
import { summary, findings } from '../fixtures/api'

beforeEach(() => setActivePinia(createPinia()))

describe('dashboard store', () => {
  it('exposes loading, data and last success; retains data only on non-auth refresh errors', async () => {
    const store = useDashboardStore()
    const api = { ...createAdminApi(), summary: vi.fn().mockResolvedValue(summary) }
    const pending = store.load(api)
    expect(store.loading).toBe(true)
    await pending
    expect(store.loading).toBe(false)
    expect(store.lastSuccess).not.toBeNull()
    api.summary.mockRejectedValueOnce(new AdminApiError(failure(503)))
    await store.load(api)
    expect(store.data?.new_records.total).toBe(0)
    expect(store.error?.status).toBe(503)
    api.summary.mockRejectedValueOnce(new AdminApiError(failure(401)))
    await store.load(api)
    expect(store.data).toBeNull()
  })
  it('ignores an older response after a rapid period change', async () => {
    let resolveOld: (value: DashboardSummary) => void = () => {}
    const old = new Promise<DashboardSummary>((resolve) => {
      resolveOld = resolve
    })
    const api = {
      ...createAdminApi(),
      summary: vi
        .fn()
        .mockReturnValueOnce(old)
        .mockResolvedValueOnce({ ...summary, period: '7d' }),
    }
    const store = useDashboardStore()
    const first = store.load(api)
    await store.setPeriod('7d', api)
    resolveOld(summary)
    await first
    expect(store.data?.period).toBe('7d')
  })
})

describe('findings store', () => {
  it('keeps the newer filtered result when an older request finishes last', async () => {
    let resolveOld: (value: typeof findings) => void = () => {}
    const old = new Promise<typeof findings>((resolve) => {
      resolveOld = resolve
    })
    const empty = {
      ...findings,
      items: [],
      pagination: { page: 1, page_size: 50, total: 0, pages: 0 },
    }
    const api = {
      ...createAdminApi(),
      findings: vi.fn().mockReturnValueOnce(old).mockResolvedValueOnce(empty),
    }
    const store = useFindingsStore()
    const first = store.load(api)
    store.setFilters({ severity: 'error' })
    await store.load(api)
    resolveOld(findings)
    await first
    expect(store.data?.items).toEqual([])
    expect(store.data?.pagination.total).toBe(0)
    expect(store.filters.severity).toBe('error')
    expect(store.loading).toBe(false)
  })
  it('retains findings on a server error but clears them when permission is denied', async () => {
    const api = { ...createAdminApi(), findings: vi.fn().mockResolvedValue(findings) }
    const store = useFindingsStore()
    await store.load(api)
    api.findings.mockRejectedValueOnce(new AdminApiError(failure(500)))
    await store.load(api)
    expect(store.data?.pagination.total).toBe(2)
    expect(store.error?.status).toBe(500)
    api.findings.mockRejectedValueOnce(new AdminApiError(failure(403)))
    await store.load(api)
    expect(store.data).toBeNull()
    expect(store.error?.status).toBe(403)
    expect(store.loading).toBe(false)
  })
  it('resets pagination on filter changes and uses server totals', async () => {
    const store = useFindingsStore()
    store.filters.page = 8
    store.setFilters({ severity: 'warning' })
    expect(store.filters.page).toBe(1)
    await store.load({ ...createAdminApi(), findings: vi.fn().mockResolvedValue(findings) })
    expect(store.data?.pagination.total).toBe(2)
    expect(store.data?.items).toHaveLength(1)
  })
  it('invalidates in-flight data when query or credentials change', async () => {
    let resolveOld: (value: typeof findings) => void = () => {}
    const old = new Promise<typeof findings>((resolve) => {
      resolveOld = resolve
    })
    const store = useFindingsStore()
    const pending = store.load({ ...createAdminApi(), findings: vi.fn().mockReturnValue(old) })
    store.reset()
    resolveOld(findings)
    await pending
    expect(store.data).toBeNull()
    expect(store.loading).toBe(false)
  })
})
