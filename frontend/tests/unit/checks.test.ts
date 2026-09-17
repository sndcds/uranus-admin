import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import Checks from '../../app/pages/checks.vue'
import PageHeader from '../../app/components/PageHeader.vue'
import DataListShell from '../../app/components/DataListShell.vue'
import ResultSummary from '../../app/components/ResultSummary.vue'
import PaginationBar from '../../app/components/PaginationBar.vue'
import StatusBadge from '../../app/components/StatusBadge.vue'
import EmptyState from '../../app/components/EmptyState.vue'
import { AdminApiError, failure } from '../../shared/errors'

const item = {
  id: '10000000-0000-4000-8000-000000000001',
  started_at: '2026-09-16T10:00:00Z',
  finished_at: null,
  status: 'queued',
  rule_count: 0,
  finding_count: 0,
  error_message: null,
  rule_results: {},
}
function page(status?: string) {
  return {
    items: status ? [{ ...item, status }] : [],
    pagination: { page: 1, page_size: 50, total: status ? 1 : 0, pages: status ? 1 : 0 },
  }
}
const api = { checkRuns: vi.fn(), runCheck: vi.fn() }
function render() {
  return mount(Checks, {
    global: {
      components: {
        PageHeader,
        DataListShell,
        ResultSummary,
        PaginationBar,
        StatusBadge,
        EmptyState,
      },
      stubs: { NuxtLink: { template: '<a><slot /></a>' }, RequestState: true, AppIcon: true },
    },
  })
}
beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('durable check status', () => {
  it('enqueues, polls queued/running/success and stops on completion', async () => {
    api.checkRuns
      .mockResolvedValueOnce(page())
      .mockResolvedValueOnce(page('queued'))
      .mockResolvedValueOnce(page('running'))
      .mockResolvedValueOnce(page('success'))
    api.runCheck.mockResolvedValue(item)
    const wrapper = render()
    await flushPromises()
    await wrapper.get('button.button-primary').trigger('click')
    await flushPromises()
    expect(api.runCheck).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('Wartet auf Worker')
    expect(wrapper.get('button.button-primary').attributes('disabled')).toBeDefined()
    await vi.advanceTimersByTimeAsync(2000)
    expect(wrapper.text()).toContain('Läuft')
    await vi.advanceTimersByTimeAsync(2000)
    expect(wrapper.text()).toContain('Erfolgreich')
    expect(wrapper.get('button.button-primary').attributes('disabled')).toBeUndefined()
    await vi.advanceTimersByTimeAsync(10000)
    expect(api.checkRuns).toHaveBeenCalledTimes(4)
    wrapper.unmount()
  })
  it('keeps failure visible and stops polling', async () => {
    api.checkRuns.mockResolvedValueOnce(page('running')).mockResolvedValueOnce(page('failed'))
    const wrapper = render()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    expect(wrapper.text()).toContain('Prüfung fehlgeschlagen')
    await vi.advanceTimersByTimeAsync(10000)
    expect(api.checkRuns).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
  it('clears data on auth loss and cancels polling on unmount', async () => {
    api.checkRuns
      .mockResolvedValueOnce(page('running'))
      .mockRejectedValue(new AdminApiError(failure(401)))
    const wrapper = render()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(wrapper.findAll('li')).toHaveLength(0)
    await vi.advanceTimersByTimeAsync(10000)
    expect(api.checkRuns).toHaveBeenCalledTimes(2)
    wrapper.unmount()
    api.checkRuns.mockResolvedValue(page('queued'))
    const next = render()
    await flushPromises()
    next.unmount()
    await vi.advanceTimersByTimeAsync(10000)
    expect(api.checkRuns).toHaveBeenCalledTimes(3)
  })
})
