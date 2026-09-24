import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SqlQueryPanel from '../../app/components/sql/SqlQueryPanel.vue'
import SqlWorkspace from '../../app/components/sql/SqlWorkspace.vue'

const base = {
  sql: 'SELECT 1;',
  copySql: 'SELECT 1;',
  description: 'READ ONLY',
  parameters: {},
  executable: true,
  running: false,
  error: '',
  result: null,
  page: true,
}
describe('SQL workspace presentation', () => {
  it.each([
    ['Idle', 'Bereit'],
    ['Running', 'Wird ausgeführt'],
    ['Cancelling', 'Wird abgebrochen'],
    ['Cancelled', 'Abgebrochen'],
    ['Completed', 'Abgeschlossen'],
    ['Error', 'Fehler'],
  ])('presents %s as text while preserving its internal state', async (status, label) => {
    const view = mount(SqlQueryPanel, {
      props: { ...base, status },
      global: { stubs: { SqlCodeEditor: true, AppIcon: true } },
    })
    expect(view.get('.sql-query-section > [role="status"]').text()).toBe(label)
    await view.setProps({ page: false })
    expect(view.get('.sql-query-section > [role="status"]').text()).toBe(status)
    view.unmount()
  })
  it('distinguishes empty, cancelled, failure, and completed result states', async () => {
    const view = mount(SqlQueryPanel, {
      props: base,
      global: { stubs: { SqlCodeEditor: true, AppIcon: true } },
    })
    expect(view.text()).toContain('Noch keine Abfrage ausgeführt.')
    await view.setProps({ status: 'Cancelled' })
    expect(view.text()).toContain('Abfrage abgebrochen.')
    await view.setProps({
      status: 'Completed',
      result: { columns: ['value'], rows: [], row_count: 0, duration_ms: 4, observed_at: null },
    })
    expect(view.text()).toContain('Die Abfrage hat keine aktuellen Datensätze zurückgegeben.')
    await view.setProps({
      result: {
        columns: ['value'],
        rows: [{ value: '<script>fixture</script>' }],
        row_count: 1,
        duration_ms: 4,
        observed_at: null,
        truncated: true,
      },
    })
    expect(view.get('caption').text()).toBe('Diagnose-Ergebnis')
    expect(view.get('[aria-label="Ergebnistabelle"]').attributes('tabindex')).toBe('0')
    expect(view.text()).toContain('Inspektionsgrenze erreicht')
    expect(view.find('script').exists()).toBe(false)
    await view.setProps({
      result: null,
      error: 'SQL-Syntax prüfen.',
      status: 'Error',
      errorPosition: 8,
    })
    expect(view.get('[role="alert"]').text()).toContain('SQL-Syntax prüfen.')
    expect(view.get('[role="alert"]').text()).toContain('SQL-Position: 8')
    view.unmount()
  })
  it('uses a named page region without nesting main, keeping the existing dialog variant', async () => {
    const view = mount(SqlWorkspace, {
      props: { page: true },
      slots: { default: 'Query', context: 'Uranus READ ONLY' },
      global: { stubs: { AppIcon: true } },
    })
    expect(view.find('main').exists()).toBe(false)
    expect(view.get('section[aria-label="SQL-Arbeitsfläche"]').text()).toBe('Query')
    expect(view.get('aside[aria-label="Datenbankkontext"]').text()).toContain('READ ONLY')
    await view.setProps({ page: false })
    expect(view.get('main').text()).toBe('Query')
    expect(view.classes()).toContain('md:grid-cols-[260px_minmax(0,1fr)]')
    view.unmount()
  })
})
