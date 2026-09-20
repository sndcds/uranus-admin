import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ref, onBeforeUnmount } from 'vue'
import SqlDiagnosticPanel from '../../app/components/sql/SqlDiagnosticPanel.vue'
import { diagnosticDefinition, diagnosticResult } from '../fixtures/sql-diagnostics'
import { AdminApiError, failure } from '../../shared/errors'
import { sqlDiagnosticResultSchema } from '../../shared/contracts'
import { createAdminApi } from '../../app/utils/admin-api'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'
const api = { sqlDiagnostic: vi.fn(), executeSqlDiagnostic: vi.fn() }
beforeEach(() => {
  vi.stubGlobal('ref', ref)
  vi.stubGlobal('onBeforeUnmount', onBeforeUnmount)
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
  api.sqlDiagnostic.mockReset().mockResolvedValue(diagnosticDefinition)
  api.executeSqlDiagnostic.mockReset().mockResolvedValue(diagnosticResult)
})
afterEach(() => vi.unstubAllGlobals())
async function expand(view: ReturnType<typeof mount>) {
  const details = view.get('details')
  ;(details.element as HTMLDetailsElement).open = true
  await details.trigger('toggle')
  await flushPromises()
}
describe('SQL diagnostics', () => {
  it('loads lazily, copies rendered SQL and executes only the persisted finding ID', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    const view = mount(SqlDiagnosticPanel, { props: { findingId: 'historical-finding' } })
    expect(api.sqlDiagnostic).not.toHaveBeenCalled()
    expect(api.executeSqlDiagnostic).not.toHaveBeenCalled()
    await expand(view)
    expect(view.get('code').text()).toBe(diagnosticDefinition.sql)
    expect(api.executeSqlDiagnostic).not.toHaveBeenCalled()
    await view
      .findAll('button')
      .find((button) => button.text() === 'SQL kopieren')!
      .trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith(diagnosticDefinition.copy_sql)
    expect(view.text()).toContain('SQL kopiert')
    await view
      .findAll('button')
      .find((button) => button.text() === 'Prüfen')!
      .trigger('click')
    await flushPromises()
    expect(api.executeSqlDiagnostic).toHaveBeenCalledExactlyOnceWith('historical-finding')
    expect(view.text()).toContain('TRUE')
    expect(view.get('table').text()).toContain('point_missing')
    view.unmount()
  })
  it('shows current non-matching historical evaluation', async () => {
    api.executeSqlDiagnostic.mockResolvedValue({
      ...diagnosticResult,
      rows: diagnosticResult.rows.map((row) => ({ ...row, point_missing: false })),
      evaluation: {
        ...diagnosticResult.evaluation,
        matched: false,
        message: 'Aktueller Datenstand erfüllt die Regel nicht mehr.',
        checks: [],
      },
    })
    const view = mount(SqlDiagnosticPanel, { props: { findingId: 'resolved' } })
    await expand(view)
    await view
      .findAll('button')
      .find((button) => button.text() === 'Prüfen')!
      .trigger('click')
    await flushPromises()
    expect(view.text()).toContain('Aktueller Datenstand erfüllt die Regel nicht mehr.')
    view.unmount()
  })
  it.each([
    ['diagnostic_unavailable', 'Keine SQL-Diagnose verfügbar.'],
    ['diagnostic_timeout', 'Query überschritt Zeitlimit.'],
    ['diagnostic_failed', 'Prüfung fehlgeschlagen.'],
  ])('handles %s safely', async (code, message) => {
    api.sqlDiagnostic.mockRejectedValue(new AdminApiError(failure(503, code)))
    const view = mount(SqlDiagnosticPanel, { props: { findingId: 'unsupported' } })
    await expand(view)
    expect(view.get('[role="alert"]').text()).toBe(message)
    expect(api.executeSqlDiagnostic).not.toHaveBeenCalled()
    view.unmount()
  })
  it('shows loading and discards a late result after unmount', async () => {
    let complete: (value: unknown) => void = () => {}
    api.sqlDiagnostic.mockReturnValue(
      new Promise((resolve) => {
        complete = resolve
      }),
    )
    const view = mount(SqlDiagnosticPanel, { props: { findingId: 'first' } })
    await expand(view)
    expect(view.text()).toContain('Diagnose laden…')
    view.unmount()
    complete(diagnosticDefinition)
    await flushPromises()
  })
  it('shows execution progress and a safe timeout without stale result rows', async () => {
    let reject: (error: unknown) => void = () => {}
    api.executeSqlDiagnostic.mockReturnValue(
      new Promise((_resolve, fail) => {
        reject = fail
      }),
    )
    const view = mount(SqlDiagnosticPanel, { props: { findingId: 'finding' } })
    await expand(view)
    const button = view.findAll('button').find((item) => item.text() === 'Prüfen')!
    await button.trigger('click')
    expect(view.text()).toContain('Prüfung läuft…')
    expect(button.attributes('disabled')).toBeDefined()
    reject(new AdminApiError(failure(504, 'diagnostic_timeout')))
    await flushPromises()
    expect(view.get('[role="alert"]').text()).toBe('Query überschritt Zeitlimit.')
    expect(view.find('table').exists()).toBe(false)
    expect(button.attributes('disabled')).toBeUndefined()
    view.unmount()
  })
  it('rejects secret result columns before the panel can render them', async () => {
    const leaked = {
      ...diagnosticResult,
      columns: ['accept_token'],
      rows: [{ accept_token: 'TOP-SECRET-FIXTURE' }],
    }
    expect(sqlDiagnosticResultSchema.safeParse(leaked).success).toBe(false)
    const client = createAdminApi(vi.fn().mockResolvedValue(new Response(JSON.stringify(leaked))))
    await expect(client.executeSqlDiagnostic('finding')).rejects.not.toThrow('TOP-SECRET-FIXTURE')
  })
  it('uses typed definition and execute contracts through the bounded proxy', async () => {
    const fetcher = vi
      .fn()
      .mockImplementation(async () => new Response(JSON.stringify(diagnosticResult)))
    const input = {
      path: '/api/v1/findings/sql-diagnostic/execute',
      method: 'POST',
      query: new URLSearchParams(),
      authorization: 'Bearer fixture',
      body: { finding_id: 'persisted' },
    }
    const base = 'http://127.0.0.1:8000'
    expect((await forwardAdminRequest(input, base, fetcher)).status).toBe(200)
    expect(fetcher.mock.calls[0]?.[1].body).toBe(JSON.stringify({ finding_id: 'persisted' }))
    for (const key of ['sql', 'parameters', 'recipe_id', 'limit']) {
      expect(
        (
          await forwardAdminRequest(
            { ...input, body: { ...input.body, [key]: 'forbidden' } },
            base,
            fetcher,
          )
        ).status,
      ).toBe(422)
    }
    expect(
      (await forwardAdminRequest({ ...input, method: 'GET', body: undefined }, base, fetcher))
        .status,
    ).toBe(405)
    expect(
      (
        await forwardAdminRequest(
          { ...input, path: '/api/v1/findings/sql-diagnostic' },
          base,
          fetcher,
        )
      ).status,
    ).toBe(405)
    for (const query of [
      new URLSearchParams(),
      new URLSearchParams('finding_id=x&finding_id=y'),
      new URLSearchParams({ finding_id: 'x'.repeat(8193) }),
    ]) {
      expect(
        (
          await forwardAdminRequest(
            {
              ...input,
              path: '/api/v1/findings/sql-diagnostic',
              method: 'GET',
              body: undefined,
              query,
            },
            base,
            fetcher,
          )
        ).status,
      ).toBe(422)
    }
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
})
