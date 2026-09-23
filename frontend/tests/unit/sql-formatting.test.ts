import { describe, it, expect, vi } from 'vitest'
import { formatPostgresql } from '../../app/utils/sql-formatter'
import { formatSql } from '../../app/utils/sql-format'
import { sqlCsv } from '../../app/utils/sql-csv'
import { sqlFindingLink, sqlFindingFromHash } from '../../app/utils/sql-finding-link'
import fixtures from '../fixtures/sql-provenance.json'
import { diagnosticDefinition } from '../fixtures/sql-diagnostics'
import { findings } from '../fixtures/api'

describe('PostgreSQL presentation', () => {
  it('formats the requested example with four spaces and compact clauses', () => {
    expect(
      formatPostgresql(
        'SELECT uuid,event_uuid,start_date FROM uranus.event_date WHERE uuid = :entity_key LIMIT :diagnostic_limit',
      ),
    ).toBe(
      'SELECT\n    uuid,\n    event_uuid,\n    start_date\nFROM uranus.event_date\nWHERE uuid = :entity_key\nLIMIT :diagnostic_limit;',
    )
  })
  it('lays out JOIN, ON, boolean conditions, GROUP/HAVING/ORDER and LIMIT', () => {
    const sql =
      'SELECT d.uuid,count(e.uuid) FROM uranus.event_date AS d LEFT JOIN uranus.event AS e ON e.uuid=d.event_uuid WHERE d.uuid=:entity_key AND e.uuid IS NOT NULL GROUP BY d.uuid HAVING count(e.uuid)>0 ORDER BY d.uuid LIMIT 50'
    const result = formatPostgresql(sql)
    for (const text of [
      '\nFROM uranus.event_date AS d',
      '\nLEFT JOIN uranus.event AS e\n    ON e.uuid = d.event_uuid',
      '\nWHERE d.uuid = :entity_key',
      '\n    AND e.uuid IS NOT NULL',
      '\nGROUP BY d.uuid',
      '\nHAVING count(e.uuid) > 0',
      '\nORDER BY d.uuid',
      '\nLIMIT 50;',
    ])
      expect(result).toContain(text)
  })
  it('preserves PostgreSQL casts, quoted names, binds, URLs and string contents', () => {
    const literal = "'https://example.test/a?x=:entity_key&y=::text&z=''SELECT''\nFROM test'"
    const dollar = '$tag$ON x\nLIMIT\n  :param; <script>$tag$'
    const sql = `SELECT release_status::text, "Odd Name", :entity_key, ${literal}, ${dollar}, E'it\\'s escaped' FROM uranus.event`
    const result = formatPostgresql(sql)
    for (const value of [
      'release_status::text',
      '"Odd Name"',
      ':entity_key',
      literal,
      dollar,
      "E'it\\'s escaped'",
    ])
      expect(result).toContain(value)
    expect(result).toContain('SELECT\n')
  })
  it('formats CTEs, CASE, EXISTS and subqueries without rewriting values', () => {
    const result = formatPostgresql(
      "WITH dates AS (SELECT uuid FROM uranus.event_date WHERE uuid=:id) SELECT CASE WHEN EXISTS (SELECT uuid FROM dates) THEN 'yes' ELSE 'no' END AS available FROM dates",
    )
    for (const text of [
      'WITH',
      'dates AS (',
      'SELECT\n',
      'CASE',
      'WHEN EXISTS',
      "THEN 'yes'",
      "ELSE 'no'",
      'END AS available',
    ])
      expect(result).toContain(text)
  })
  it('preserves comments and newline-sensitive adjacent literals', () => {
    for (const sql of [
      "SELECT 'a'\n'b'",
      "SELECT 'a' 'b'",
      'SELECT 1 /* outer /* inner */ ON x */ -- tail',
      "SELECT 'line\nLIMIT\n  4' -- last;",
    ]) {
      const result = formatPostgresql(sql)
      if (sql.includes("'a'\n'b'")) expect(result).toContain("'a'\n'b'")
      if (sql.includes('/* outer')) expect(result).toContain('/* outer /* inner */ ON x */')
      if (sql.includes("'line")) expect(result).toContain("'line\nLIMIT\n  4'")
    }
  })
  it('is idempotent for every registered fixture and formats bound copy_sql separately', async () => {
    const queries = [
      diagnosticDefinition,
      ...Object.values(fixtures).flatMap((value) => value.sources),
    ]
    for (const source of queries) {
      for (const sql of [source.sql, source.copy_sql].filter(
        (sql): sql is string => sql !== null,
      )) {
        const formatted = await formatSql(sql)
        expect(formatPostgresql(formatted)).toBe(formatted)
        expect(formatted.length).toBeGreaterThan(0)
      }
    }
    const copy = await formatSql(diagnosticDefinition.copy_sql)
    expect(copy).toContain('\n')
    expect(copy).toContain("'00000000-0000-4000-8000-000000000020'")
    expect(copy).not.toContain(':entity_key')
  })
  it('returns readable raw SQL for unsupported syntax or oversized input', () => {
    for (const sql of ['SELECT `unsupported`', 'x'.repeat(200_001), ''])
      expect(formatPostgresql(sql)).toBe(sql)
  })
  it('falls back if the optional formatter chunk cannot load', async () => {
    vi.doMock('../../app/utils/sql-formatter', () => {
      throw new Error('chunk unavailable')
    })
    expect(await formatSql('SELECT 1')).toBe('SELECT 1')
    vi.doUnmock('../../app/utils/sql-formatter')
  })
})
it('exports only loaded columns/rows, escapes CSV and neutralizes string formulas', () => {
  expect(
    sqlCsv(
      ['value', 'nullable'],
      [
        { value: 'a,"b"\nc', nullable: null },
        { value: '=1+1', nullable: false },
        { value: '  @SUM(A1)', nullable: -3 },
      ],
    ),
  ).toBe('"value","nullable"\r\n"a,""b""\nc",""\r\n"\'=1+1","false"\r\n"\'  @SUM(A1)","-3"\r\n')
})
it('opens only a supported finding returned by the authenticated list', () => {
  const finding = { ...findings.items[0]!, sql_diagnostic_available: true }
  const url = new URL(sqlFindingLink(finding), 'https://admin.example')
  expect(url.pathname).toBe('/findings')
  expect(url.searchParams.get('entity_key')).toBe(finding.entity_key)
  expect(sqlFindingFromHash(url.hash, [finding])).toEqual(finding)
  expect(
    sqlFindingFromHash(url.hash, [{ ...finding, sql_diagnostic_available: false }]),
  ).toBeUndefined()
  expect(sqlFindingFromHash('#sql-editor=%XX', [finding])).toBeUndefined()
  expect(sqlFindingFromHash('#sql-editor=unknown', [finding])).toBeUndefined()
})

it('keeps live SQL hash links in live mode', () => {
  const finding = { ...findings.items[0]!, sql_diagnostic_available: true }
  const url = new URL(sqlFindingLink(finding, 'live'), 'https://admin.example')
  expect(url.searchParams.get('mode')).toBe('live')
  expect(sqlFindingFromHash(url.hash, [finding])).toEqual(finding)
})
