import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { useTemplateRef } from 'vue'
import SqlEditorModal from '../../app/components/sql/SqlEditorModal.vue'
import SqlCodeEditor from '../../app/components/sql/SqlCodeEditor.vue'
import SqlParameterTable from '../../app/components/sql/SqlParameterTable.vue'
import SqlResultTable from '../../app/components/sql/SqlResultTable.vue'
import FindingsList from '../../app/components/FindingsList.vue'
import { diagnosticDefinition, diagnosticResult } from '../fixtures/sql-diagnostics'
import { findings } from '../fixtures/api'
import { AdminApiError, failure } from '../../shared/errors'
import { findingSchema, sqlDiagnosticResultSchema } from '../../shared/contracts'
import { createAdminApi } from '../../app/utils/admin-api'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'
const api = { sqlDiagnostic: vi.fn(), executeSqlDiagnostic: vi.fn() }
const finding = { ...findings.items[0]!, sql_diagnostic_available: true }
const views: ReturnType<typeof mount>[] = []
beforeEach(() => {
  vi.stubGlobal('useTemplateRef', useTemplateRef)
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
  vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function () {
    this.open = true
  })
  vi.spyOn(HTMLDialogElement.prototype, 'close').mockImplementation(function () {
    this.open = false
  })
  api.sqlDiagnostic.mockReset().mockResolvedValue(diagnosticDefinition)
  api.executeSqlDiagnostic.mockReset().mockResolvedValue(diagnosticResult)
})
afterEach(() => {
  views.splice(0).forEach((view) => view.unmount())
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
function setup() {
  const view = mount(SqlEditorModal, { global: { stubs: { AppIcon: true } } })
  views.push(view)
  return view
}
async function open(view: ReturnType<typeof setup>, value = finding) {
  view.vm.open(value)
  await flushPromises()
}
async function click(view: ReturnType<typeof mount>, text: string) {
  await view
    .findAll('button')
    .find((button) => button.text() === text)!
    .trigger('click')
  await flushPromises()
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (cause: unknown) => void
  const promise = new Promise<T>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}
describe('SQL editor', () => {
  it('defaults old finding responses to unavailable and validates the capability', () => {
    const { sql_diagnostic_available: _capability, ...legacy } = finding
    expect(findingSchema.parse(legacy).sql_diagnostic_available).toBe(false)
    expect(findingSchema.safeParse({ ...legacy, sql_diagnostic_available: 'true' }).success).toBe(
      false,
    )
  })
  it('renders NULL, booleans and escaped result values in a semantic table', () => {
    const view = mount(SqlResultTable, {
      props: {
        columns: ['uuid', 'point', 'point_missing'],
        rows: [{ uuid: '<script>not markup</script>', point: null, point_missing: false }],
      },
    })
    views.push(view)
    expect(view.get('table').text()).toContain('NULL')
    expect(view.get('table').text()).toContain('false')
    expect(view.find('script').exists()).toBe(false)
    expect(view.get('thead').classes()).toContain('sticky')
  })
  it('loads lazily, copies executable SQL and executes only the persisted finding ID', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    const view = setup()
    expect(api.sqlDiagnostic).not.toHaveBeenCalled()
    await open(view)
    expect(view.get('dialog').classes()).toContain('max-w-5xl')
    expect(view.text()).toContain('READ ONLY')
    expect(view.text()).toContain(finding.entity_name)
    expect(view.text()).toContain('Parameter')
    expect(view.get('code').text()).toBe(diagnosticDefinition.sql)
    expect(api.executeSqlDiagnostic).not.toHaveBeenCalled()
    await click(view, 'SQL kopieren')
    expect(writeText).toHaveBeenCalledExactlyOnceWith(diagnosticDefinition.copy_sql)
    expect(view.text()).toContain('SQL kopiert')
    await click(view, 'Abfrage ausführen')
    expect(api.executeSqlDiagnostic).toHaveBeenCalledExactlyOnceWith(finding.id)
    expect(view.text()).toContain('Der aktuelle Datenstand erfüllt weiterhin die Finding-Regel.')
    expect(view.get('table caption').text()).toBe('Gebundene SQL-Parameter')
    expect(view.get('[aria-label="Ergebnistabelle"]').text()).toContain('point_missing')
    expect(view.text()).toContain('1 Zeile')
  })
  it.each([
    [false, 'Der aktuelle Datenstand erfüllt diese Regel nicht mehr.'],
    [null, 'Die Regel konnte für den aktuellen Datenstand nicht ausgewertet werden.'],
  ])(
    'explains matched=%s for resolved findings, including empty results',
    async (matched, message) => {
      api.executeSqlDiagnostic.mockResolvedValue({
        ...diagnosticResult,
        rows: [],
        row_count: 0,
        evaluation: { ...diagnosticResult.evaluation, matched },
      })
      const view = setup()
      await open(view, { ...finding, status: 'resolved' })
      await click(view, 'Abfrage ausführen')
      expect(view.text()).toContain(message)
      expect(view.text()).toContain('Die Abfrage hat keine aktuellen Datensätze zurückgegeben.')
      expect(view.text()).toContain('Finding zuletzt beobachtet')
      expect(view.text()).toContain('Aktuelle Diagnose:')
    },
  )
  it('resets results and copy feedback on close and reopen', async () => {
    const view = setup()
    await open(view)
    await click(view, 'Abfrage ausführen')
    await click(view, 'SQL kopieren')
    await view.get('[aria-label="SQL Editor schließen"]').trigger('click')
    expect(view.find('code').exists()).toBe(false)
    await open(view)
    expect(view.text()).toContain('Noch keine Abfrage ausgeführt.')
    expect(view.text()).not.toContain('SQL kopiert')
    expect(view.find('[aria-label="Ergebnistabelle"]').exists()).toBe(false)
  })
  it('discards a late definition when A is replaced by B', async () => {
    const first = deferred<typeof diagnosticDefinition>()
    api.sqlDiagnostic.mockReturnValueOnce(first.promise)
    const view = setup()
    await open(view)
    expect(view.text()).toContain('SQL-Diagnose wird geladen…')
    await open(view, { ...finding, id: 'B', entity_name: 'Finding B' })
    first.resolve({ ...diagnosticDefinition, sql: 'STALE A' })
    await flushPromises()
    expect(view.text()).toContain('Finding B')
    expect(view.get('code').text()).toBe(diagnosticDefinition.sql)
  })
  it('discards a late execution when A is replaced by B', async () => {
    const first = deferred<typeof diagnosticResult>()
    api.executeSqlDiagnostic.mockReturnValueOnce(first.promise)
    const view = setup()
    await open(view)
    await click(view, 'Abfrage ausführen')
    expect(view.text()).toContain('Abfrage wird ausgeführt…')
    await open(view, { ...finding, id: 'B' })
    first.resolve(diagnosticResult)
    await flushPromises()
    expect(view.text()).toContain('Noch keine Abfrage ausgeführt.')
    expect(view.find('[aria-label="Ergebnistabelle"]').exists()).toBe(false)
  })
  it('shows safe definition errors and supports retry', async () => {
    api.sqlDiagnostic.mockRejectedValueOnce(
      new AdminApiError(failure(503, 'diagnostic_unavailable')),
    )
    const view = setup()
    await open(view)
    expect(view.get('[role="alert"]').text()).toContain('Keine SQL-Diagnose verfügbar.')
    await click(view, 'Erneut versuchen')
    expect(view.get('code').text()).toBe(diagnosticDefinition.sql)
    expect(api.executeSqlDiagnostic).not.toHaveBeenCalled()
  })
  it('disables execution while pending and shows a safe timeout', async () => {
    const execution = deferred<typeof diagnosticResult>()
    api.executeSqlDiagnostic.mockReturnValue(execution.promise)
    const view = setup()
    await open(view)
    await click(view, 'Abfrage ausführen')
    const button = view.findAll('button').find((item) => item.text() === 'Abfrage ausführen')!
    expect(button.attributes('disabled')).toBeDefined()
    execution.reject(new AdminApiError(failure(504, 'diagnostic_timeout')))
    await flushPromises()
    expect(view.get('[role="alert"]').text()).toContain('Query überschritt Zeitlimit.')
    expect(button.attributes('disabled')).toBeUndefined()
  })
  it('highlights structured SQL without changing its text or interpreting HTML', async () => {
    const sql =
      "SELECT :entity_key, 42, '<img src=x onerror=alert(1)>'\nFROM uranus.venue -- comment"
    const view = mount(SqlCodeEditor, { props: { sql } })
    views.push(view)
    await vi.waitFor(() => expect(view.find('.token.keyword').exists()).toBe(true))
    expect(view.get('code').element.textContent).toBe(sql)
    expect(view.get('.token.parameter').text()).toBe(':entity_key')
    expect(view.find('img').exists()).toBe(false)
    expect(view.get('[aria-hidden="true"]').classes()).toContain('select-none')
    await view.setProps({ sql: 'SELECT false' })
    await flushPromises()
    expect(view.get('code').text()).toBe('SELECT false')
  })
  it('derives parameter types without changing values', () => {
    const view = mount(SqlParameterTable, {
      props: {
        parameters: {
          ...diagnosticDefinition.parameters,
          enabled: false,
          date: '2026-09-20',
          observed: '2026-09-20T12:00:00Z',
          absent: null,
          text: '<script>',
        },
      },
    })
    views.push(view)
    for (const type of ['UUID', 'Integer', 'Boolean', 'Date', 'DateTime', 'NULL', 'String'])
      expect(view.text()).toContain(type)
    expect(view.find('script').exists()).toBe(false)
  })
  it('shows SQL Editor only for supported findings and retains details', async () => {
    const view = mount(FindingsList, {
      props: {
        items: [
          finding,
          {
            ...finding,
            id: 'unsupported',
            entity_name: 'Unsupported',
            sql_diagnostic_available: false,
          },
        ],
      },
      global: {
        stubs: {
          FindingDetail: true,
          RecordMarkLink: true,
          AppIcon: true,
          SeverityBadge: true,
          EntityTypeBadge: true,
          StatusBadge: true,
        },
      },
    })
    views.push(view)
    const rows = view.findAll('li')
    expect(rows[0]!.text()).toContain('SQL Editor')
    expect(rows[0]!.text()).toContain('Details')
    expect(rows[0]!.text()).not.toContain('Ansehen')
    expect(rows[1]!.text()).not.toContain('SQL Editor')
    expect(rows[1]!.text()).toContain('Ansehen')
    await view.get('[aria-label="SQL Editor für Test-Hafenbühne"]').trigger('click')
    await flushPromises()
    expect(view.get('dialog').attributes('open')).toBeDefined()
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
