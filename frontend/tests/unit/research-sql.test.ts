import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { computed } from 'vue'
import ResearchQueryAnswer from '../../app/components/ResearchQueryAnswer.vue'
import EmptyState from '../../app/components/EmptyState.vue'
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
import v9Cases from '../fixtures/research-v9-parity.json' with { type: 'json' }
import calendarCases from '../fixtures/research-calendar-v10.json' with { type: 'json' }

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
    global: {
      components: { EmptyState },
      stubs: { AppIcon: true, ResearchResult: true, NuxtLink: true },
    },
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
  expect(table.findAll('thead th').map((column) => column.text())).toEqual([
    'Veranstaltungstyp',
    'Monat',
    'Termine',
  ])
  expect(table.text()).toContain('Konzert')
  expect(table.findAll('tbody th, tbody td').map((cell) => cell.text())).toEqual([
    'Konzert',
    'September',
    '7',
  ])
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

it.each([
  ['01', 'Januar'],
  ['03', 'März'],
  ['09', 'September'],
  ['10', 'Oktober'],
  ['12', 'Dezember'],
  ['unknown', 'unknown'],
])('renders month %s as %s without mutating the response', (value, label) => {
  const response = groupedExecutionResponse()
  if (response.result.kind !== 'grouped') throw new Error('Expected grouped fixture')
  const coordinate = response.result.items[0]!.coordinates[1]!
  coordinate.key = value
  coordinate.name = value
  const original = structuredClone(response)
  const table = answer(response).get('table[aria-label="Mehrdimensionale Auswertung"]')
  expect(table.findAll('tbody th, tbody td').map((cell) => cell.text())).toEqual([
    'Konzert',
    label,
    '7',
  ])
  expect(response).toEqual(original)
  expect(researchExecutionResponseSchema.parse(response)).toEqual(original)
})

it.each(['grouped', 'aggregate', 'comparison'] as const)(
  'uses consistent semantic table styling for %s results',
  (kind) => {
    const response = kind === 'grouped' ? groupedExecutionResponse() : executionResponse(kind)
    const table = answer(response).get('table')
    expect(table.element.parentElement!.classList.contains('overflow-x-auto')).toBe(true)
    expect(table.get('thead tr').classes()).toContain('border-b')
    for (const header of table.findAll('thead th')) {
      expect(header.attributes('scope')).toBe('col')
      expect(header.classes()).toContain('p-2')
    }
    expect(table.get('thead th:last-child').classes()).toContain('text-right')
    for (const row of table.findAll('tbody tr')) {
      expect(row.classes()).toContain('border-b')
      expect(row.get('th:first-child').attributes('scope')).toBe('row')
      expect(row.get('th:first-child').classes()).toContain('font-normal')
      for (const cell of row.findAll('th, td')) expect(cell.classes()).toContain('p-2')
      expect(row.get('td:last-child').classes()).toEqual(
        expect.arrayContaining(['text-right', 'tabular-nums']),
      )
    }
  },
)

it.each(['grouped', 'aggregate'] as const)('shows the same empty-state feedback for %s', (kind) => {
  const response = kind === 'grouped' ? groupedExecutionResponse() : executionResponse(kind)
  if (response.result.kind !== 'grouped' && response.result.kind !== 'aggregate') {
    throw new Error('Expected grouped or aggregate fixture')
  }
  response.result.items = []
  const view = answer(response)
  expect(view.getComponent(EmptyState).text()).toBe('Keine Gruppen für diese Auswertung.')
  expect(view.findAll('tbody tr')).toHaveLength(0)
  expect(view.get('button[aria-label="SQL Editor"]').text()).toBe('SQL Editor')
})

it('keeps grouped results visible without offering an empty SQL Editor', () => {
  const view = answer({ ...groupedExecutionResponse(), sql_provenance: [] })
  expect(view.find('table[aria-label="Mehrdimensionale Auswertung"]').exists()).toBe(true)
  expect(view.find('button[aria-label="SQL Editor"]').exists()).toBe(false)
  expect(view.findComponent(ResearchSqlEditorModal).exists()).toBe(false)
})

it.each([
  ['event_count', 'count', 'Veranstaltungen'],
  ['aggregate-venue', 'aggregate', 'Veranstaltungsort'],
  ['compare-area', 'comparison', 'Vergleich'],
  ['semantic', 'records', 'Semantische Relevanz'],
  ['chronological-desc', 'records', 'Startdatum'],
] as const)('renders %s through the same response and SQL Editor', async (name, kind, label) => {
  const plan = v9Cases.find((item) => item.name === name)!.plan
  const base = executionResponse(kind, name === 'semantic')
  const envelope = groupedExecutionResponse().plan
  const response = researchExecutionResponseSchema.parse({
    ...base,
    query: plan.original_query,
    plan: {
      ...envelope,
      plan,
      diagnostics: { ...envelope.diagnostics, planner_intent: plan.intent },
    },
  })
  const view = answer(response)
  expect(view.text()).toContain(label)
  await view.get('button[aria-label="SQL Editor"]').trigger('click')
  await flushPromises()
  expect(view.getComponent(SqlCodeEditor).props('readonly')).toBe(true)
  expect(view.getComponent(SqlCodeEditor).props('sql')).toBe(response.sql_provenance[0]!.sql)
})

it.each(['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'])(
  'renders %s in the common grouped table and preserves read-only SQL',
  async (label) => {
    const day =
      ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'].indexOf(
        label,
      ) + 1
    const base = groupedExecutionResponse()
    const plan = calendarCases.find((c) => c.name === 'weekday-distribution')!.plan
    const response = researchExecutionResponseSchema.parse({
      ...base,
      query: plan.original_query,
      plan: {
        ...base.plan,
        schema_version: 'research-query-plan-v10',
        prompt_version: 'research-planner-v16',
        plan,
        diagnostics: { ...base.plan.diagnostics, planner_prompt_version: 'research-planner-v16' },
      },
      result: {
        ...base.result,
        dimensions: ['event_type', 'weekday'],
        items: [
          {
            coordinates: [
              { dimension: 'event_type', key: '1', name: 'Konzert' },
              { dimension: 'weekday', key: String(day), name: String(day) },
            ],
            value: 7,
          },
        ],
      },
    })
    const view = answer(response)
    const table = view.get('table[aria-label="Mehrdimensionale Auswertung"]')
    expect(table.findAll('thead th').map((cell) => cell.text())).toEqual([
      'Veranstaltungstyp',
      'Wochentag',
      'Termine',
    ])
    expect(table.findAll('tbody th, tbody td').map((cell) => cell.text())).toEqual([
      'Konzert',
      label,
      '7',
    ])
    await view.get('button[aria-label="SQL Editor"]').trigger('click')
    await flushPromises()
    expect(view.getComponent(SqlCodeEditor).props('readonly')).toBe(true)
    expect(view.getComponent(SqlCodeEditor).props('sql')).toBe(response.sql_provenance[0]!.sql)
  },
)

it.each(['count', 'records', 'aggregate', 'comparison'] as const)(
  'renders backend answer_text verbatim next to the existing %s detail',
  (kind) => {
    const response = executionResponse(kind)
    response.answer_text = 'Backend-Antwort: <sicher> & unverändert.'
    const view = answer(response)
    expect(view.get('[data-testid=research-answer-summary]').text()).toBe(response.answer_text)
    expect(view.find('sicher').exists()).toBe(false)
    expect(view.get('button[aria-label="SQL Editor"]').exists()).toBe(true)
    if (kind === 'count')
      expect(view.get('[data-testid=research-count]').text()).toBe('123 Veranstaltungen')
    if (kind === 'aggregate' || kind === 'comparison')
      expect(view.find('table').exists()).toBe(true)
    if (kind === 'records') expect(view.find('research-result-stub').exists()).toBe(true)
  },
)
it('renders grouped backend text without deriving extrema and keeps its table', () => {
  const response = groupedExecutionResponse()
  response.answer_text = 'Die Auswertung enthält eine angezeigte Kombination.'
  const view = answer(response)
  expect(view.get('[data-testid=research-answer-summary]').text()).toBe(response.answer_text)
  expect(view.get('table').text()).toContain('September')
  expect(view.get('[data-testid=research-answer-summary]').text()).not.toMatch(/höchst|niedrigst/)
})
it('does not fabricate prose for a nullable answer, including clarification', () => {
  for (const response of [
    executionResponse('needs_clarification'),
    { ...executionResponse(), answer_text: null },
  ]) {
    const view = answer(response)
    expect(view.find('[data-testid=research-answer-summary]').exists()).toBe(false)
  }
})
it('requires the bounded nullable answer_text field in the strict response contract', () => {
  const response = executionResponse()
  const { answer_text: _text, ...missing } = response
  expect(researchExecutionResponseSchema.safeParse(missing).success).toBe(false)
  for (const value of [true, 42, {}, 'x'.repeat(1001)]) {
    expect(
      researchExecutionResponseSchema.safeParse({ ...response, answer_text: value }).success,
    ).toBe(false)
  }
  expect(
    researchExecutionResponseSchema.safeParse({ ...response, answer_text: null }).success,
  ).toBe(true)
})
