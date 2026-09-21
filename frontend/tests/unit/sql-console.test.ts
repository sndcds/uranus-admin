import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { EditorState } from '@codemirror/state'
import { highlightSql } from '../../app/utils/sql-highlighter'
import { sqlDecorations } from '../../app/components/sql/sql-codemirror'
import { consoleClientSchema, consoleServerSchema } from '../../shared/sql-console'
import { consoleCookie, consoleUpstream } from '../../server/utils/sql-console-proxy'
import { formatPostgresql } from '../../app/utils/sql-formatter'

const sample =
  "SELECT :named_param, 123.45, 'text'::text, COUNT(*), ST_X(point) FROM uranus_console.event AS e LEFT JOIN uranus_console.event_date AS d ON e.uuid=d.event_uuid WHERE e.uuid IS NOT NULL AND TRUE OR FALSE; -- comment\n/* comment */"
it('CodeMirror maps the exact readonly Prism tokens to the same CSS classes', () => {
  const state = EditorState.create({ doc: sample })
  const decorations = sqlDecorations(state)
  const actual: { text: string; class: string }[] = []
  decorations.between(0, sample.length, (from, to, decoration) => {
    actual.push({ text: sample.slice(from, to), class: decoration.spec.class })
  })
  expect(actual).toEqual(
    highlightSql(sample)
      .filter((token) => token.type)
      .map((token) => ({ text: token.text, class: `token ${token.type}` })),
  )
  for (const type of [
    'keyword',
    'parameter',
    'number',
    'string',
    'function',
    'comment',
    'operator',
    'punctuation',
  ])
    expect(actual.some((token) => token.class === `token ${type}`)).toBe(true)
  const base = 'app/components/sql/'
  const theme = readFileSync(`${base}sql-theme.css`, 'utf8')
  const mapping = readFileSync(`${base}sql-codemirror.ts`, 'utf8')
  for (const name of ['SqlCodeEditor.vue', 'SqlReadonlyCode.vue'])
    expect(readFileSync(base + name, 'utf8')).toContain("import './sql-theme.css'")
  expect(mapping).not.toMatch(/#[\da-f]{3,8}\b/i)
  for (const name of [
    'keyword',
    'string',
    'number',
    'parameter',
    'comment',
    'operator',
    'function',
    'cast',
    'punctuation',
    'line-number',
    'selection',
    'cursor',
  ])
    expect(theme).toContain(`--sql-${name}:`)
})
it('formats exact console example and preserves named values/casts/UNION', () => {
  expect(
    formatPostgresql(
      'SELECT uuid,event_uuid,start_date FROM uranus_console.event_date WHERE uuid=:entity_key LIMIT 50',
    ),
  ).toBe(
    'SELECT\n    uuid,\n    event_uuid,\n    start_date\nFROM uranus_console.event_date\nWHERE uuid = :entity_key\nLIMIT 50;',
  )
  const formatted = formatPostgresql(
    'SELECT "Odd Name"::text FROM uranus_console.event UNION SELECT \'a::text :id\'',
  )
  expect(formatted).toContain('\nUNION\n')
  expect(formatted).toContain('"Odd Name"::text')
  expect(formatted).toContain("'a::text :id'")
})
describe('strict console transport', () => {
  const base = { v: 1, request_id: '00000000-0000-4000-8000-000000000001' }
  it('validates protocol versions, limits and empty-only params', () => {
    const request = { ...base, type: 'execute', sql: 'SELECT 1', params: {} }
    expect(consoleClientSchema.safeParse(request).success).toBe(true)
    for (const change of [
      { v: 2 },
      { row_limit: 501 },
      { params: { id: 'x' } },
      { sql: 'x'.repeat(32769) },
    ])
      expect(consoleClientSchema.safeParse({ ...request, ...change }).success).toBe(false)
    expect(
      consoleServerSchema.safeParse({ ...base, type: 'error', code: 'raw driver secret' }).success,
    ).toBe(false)
    expect(
      consoleServerSchema.safeParse({
        ...base,
        type: 'rows',
        batch: 1,
        rows: [{ value: { value: 'short', truncated: true } }],
      }).success,
    ).toBe(true)
  })
  it('rejects arbitrary upstream paths/queries/credentials and forwards only the session cookie', () => {
    expect(consoleUpstream('https://backend.example').href).toBe(
      'wss://backend.example/api/v1/sql-console/ws',
    )
    for (const base of [
      'ftp://example',
      'https://user:secret@example',
      'https://example/path',
      'https://example?sql=secret',
    ])
      expect(() => consoleUpstream(base)).toThrow()
    const token = 'a'.repeat(43)
    expect(consoleCookie(`unrelated=secret; admin_session=${token}`, true)).toBe(
      `admin_session=${token}`,
    )
    expect(consoleCookie(`admin_session=${token}`, false)).toBeNull()
    expect(consoleCookie(`admin_session=${token}; admin_session=${token}`, true)).toBeNull()
  })
})
