import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { computed } from 'vue'
import ResearchQueryAnswer from '../../app/components/ResearchQueryAnswer.vue'
import ResearchSqlEditorModal from '../../app/components/sql/ResearchSqlEditorModal.vue'
import SqlCodeEditor from '../../app/components/sql/SqlCodeEditor.vue'
import SqlParameterTable from '../../app/components/sql/SqlParameterTable.vue'
import SqlQueryPanel from '../../app/components/sql/SqlQueryPanel.vue'
import {
  researchExecutionResponseSchema,
  researchSqlStatementSchema,
} from '../../shared/research-execution'
import { executionResponse } from '../fixtures/research-execution'
import { groupedExecutionResponse } from '../fixtures/research-grouping'

const views: ReturnType<typeof mount>[] = []
beforeEach(() => {
  vi.stubGlobal('computed', computed)
  vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function () {
    this.open = true
  })
  vi.spyOn(HTMLDialogElement.prototype, 'close').mockImplementation(function () {
    this.open = false
  })
})
afterEach(() => {
  views.splice(0).forEach((view) => view.unmount())
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
function answer(response = executionResponse()) {
  const view = mount(ResearchQueryAnswer, {
    props: { response },
    global: { stubs: { AppIcon: true, ResearchResult: true, NuxtLink: true } },
  })
  views.push(view)
  return view
}
it.each(['records', 'count', 'aggregate', 'comparison'] as const)(
  'offers SQL Editor for %s with actual provenance',
  (kind) => {
    const view = answer(executionResponse(kind))
    expect(view.get('button[aria-label="SQL Editor"]').text()).toBe('SQL Editor')
    expect(view.text()).toContain('So wurde die Frage verstanden')
  },
)
it('has no SQL button or dialog without provenance, including clarification', () => {
  for (const response of [
    executionResponse('needs_clarification'),
    { ...executionResponse(), sql_provenance: [] },
  ]) {
    const view = answer(response)
    expect(view.find('button[aria-label="SQL Editor"]').exists()).toBe(false)
    expect(view.findComponent(ResearchSqlEditorModal).exists()).toBe(false)
  }
})
it('opens one statement with shared read-only editor, parameters and parameterized copy', async () => {
  const response = executionResponse()
  response.sql_provenance[0]!.parameters.place_longitude = '[Standort ausgeblendet]'
  const view = answer(response)
  await view.get('button[aria-label="SQL Editor"]').trigger('click')
  await flushPromises()
  const dialog = view.getComponent(ResearchSqlEditorModal)
  expect(dialog.getComponent(SqlCodeEditor).props('sql')).toBe(response.sql_provenance[0]!.sql)
  expect(dialog.getComponent(SqlCodeEditor).props('readonly')).toBe(true)
  expect(dialog.getComponent(SqlParameterTable).props('parameters')).toEqual(
    response.sql_provenance[0]!.parameters,
  )
  expect(dialog.getComponent(SqlParameterTable).text()).toContain('[Standort ausgeblendet]')
  expect(dialog.getComponent(SqlQueryPanel).props('copySql')).toBe(response.sql_provenance[0]!.sql)
  expect(dialog.findAll('.sql-nav')).toHaveLength(0)
  expect(dialog.text()).toContain('SQL-Abfragen der fachlichen Research-Ausführung.')
  expect(dialog.text()).toContain('READ ONLY')
  expect(dialog.text()).toContain('PostgreSQL · uranus')
  expect(dialog.text()).not.toMatch(
    /Abfrage ausführen|SQL bearbeiten|Noch keine Abfrage|nur dokumentarisch/,
  )
  expect(dialog.find('[aria-label="Ergebnis"]').exists()).toBe(false)
  await dialog.get('button[aria-label="SQL Editor schließen"]').trigger('click')
  expect(view.get('dialog').element.open).toBe(false)
})
it('selects comparison statements and resets on close and response change', async () => {
  const view = answer(executionResponse('comparison'))
  await view.get('button[aria-label="SQL Editor"]').trigger('click')
  await flushPromises()
  const buttons = view.findAll('.sql-nav')
  expect(buttons.map((button) => button.text())).toEqual([
    'Vergleich: Flensburg',
    'Vergleich: Kiel',
  ])
  await buttons[1]!.trigger('click')
  expect(buttons[1]!.attributes('aria-current')).toBe('page')
  expect(view.getComponent(SqlParameterTable).text()).toContain('Kiel')
  await view.get('button[aria-label="SQL Editor schließen"]').trigger('click')
  await view.get('button[aria-label="SQL Editor"]').trigger('click')
  await flushPromises()
  expect(view.findAll('.sql-nav')[0]!.attributes('aria-current')).toBe('page')
  await view.setProps({ response: executionResponse() })
  expect(view.get('dialog').element.open).toBe(false)
})
it('distinguishes vector ranking from SQL eligibility and rehydration', async () => {
  const view = answer(executionResponse('records', true))
  await view.get('button[aria-label="SQL Editor"]').trigger('click')
  await flushPromises()
  expect(view.text()).toContain(
    'Die semantische Rangfolge entsteht zwischen SQL-Vorauswahl und SQL-Rehydration im Vektorindex.',
  )
  expect(view.findAll('.sql-nav').map((button) => button.text())).toEqual([
    'SQL-Vorauswahl',
    'SQL-Rehydration',
  ])
  await view.findAll('.sql-nav')[1]!.trigger('click')
  expect(view.getComponent(SqlParameterTable).text()).toContain('[Standort ausgeblendet]')
})
it.each([
  { extra: true },
  { copy_sql: 'SELECT 1' },
  { kind: 'vector' },
  { label: 'x'.repeat(201) },
  { sql: '' },
  { sql: 'x'.repeat(65537) },
  { parameters: { q: 'x'.repeat(4097) } },
  { parameters: { ids: Array(101).fill('id') } },
  { parameters: { nested: { x: true } } },
  { parameters: Object.fromEntries(Array.from({ length: 65 }, (_, i) => [String(i), i])) },
  { parameters: { ['x'.repeat(65)]: 1 } },
  { parameters: { q: Infinity } },
  { parameters: { q: Number.MAX_SAFE_INTEGER + 1 } },
])('rejects unknown and oversized provenance case %#', (change) => {
  const statement = executionResponse().sql_provenance[0]!
  expect(researchSqlStatementSchema.safeParse({ ...statement, ...change }).success).toBe(false)
})
it('requires a bounded collection of closed provenance statements', () => {
  const response = executionResponse()
  expect(researchExecutionResponseSchema.parse(response)).toEqual(response)
  for (const sql_provenance of [undefined, null]) {
    expect(researchExecutionResponseSchema.safeParse({ ...response, sql_provenance }).success).toBe(
      false,
    )
  }
  expect(
    researchExecutionResponseSchema.safeParse({
      ...response,
      sql_provenance: Array(17).fill(response.sql_provenance[0]),
    }).success,
  ).toBe(false)
})

it('shows ordered grouped dimensions and their actual SQL in the shared read-only editor', async () => {
  const response = groupedExecutionResponse()
  const view = answer(response)
  const table = view.get('table[aria-label="Mehrdimensionale Auswertung"]')
  expect(table.findAll('th').map((column) => column.text())).toEqual([
    'Veranstaltungstyp',
    'Monat',
    'Termine',
  ])
  expect(table.text()).toContain('Konzert')
  expect(table.text()).toContain('09')
  expect(view.text()).toContain('So wurde die Frage verstanden')
  await view.get('button[aria-label="SQL Editor"]').trigger('click')
  await flushPromises()
  const editor = view.getComponent(SqlCodeEditor)
  expect(editor.props('readonly')).toBe(true)
  expect(editor.props('sql')).toBe(response.sql_provenance[0]!.sql)
  expect(editor.props('sql')).toContain('GROUP BY')
  expect(editor.props('sql')).toContain('extract(month FROM selected.start_date)')
  expect(editor.props('sql')).toContain('count(DISTINCT selected.date_key)')
  expect(view.getComponent(SqlParameterTable).props('parameters')).toEqual(
    response.sql_provenance[0]!.parameters,
  )
  expect(view.getComponent(SqlQueryPanel).props('copySql')).toBe(response.sql_provenance[0]!.sql)
  expect(view.text()).not.toMatch(/Abfrage ausführen|SQL bearbeiten/)
})
it('keeps grouped results visible without offering an empty SQL Editor', () => {
  const view = answer({ ...groupedExecutionResponse(), sql_provenance: [] })
  expect(view.find('table[aria-label="Mehrdimensionale Auswertung"]').exists()).toBe(true)
  expect(view.find('button[aria-label="SQL Editor"]').exists()).toBe(false)
  expect(view.findComponent(ResearchSqlEditorModal).exists()).toBe(false)
})
