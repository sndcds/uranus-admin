import type { SqlDiagnosticDefinition, SqlDiagnosticResult } from '../../shared/contracts'
export const diagnosticDefinition: SqlDiagnosticDefinition = {
  recipe_id: 'venue_missing_location',
  title: 'Veranstaltungsort ohne Geoposition',
  datasource: 'uranus',
  readonly: true,
  sql: 'SELECT\n    uuid,\n    point IS NULL AS point_missing\nFROM uranus.venue\nWHERE uuid = :entity_key\nLIMIT :diagnostic_limit',
  copy_sql:
    "SELECT uuid, point IS NULL AS point_missing FROM uranus.venue WHERE uuid = '00000000-0000-4000-8000-000000000020' LIMIT 50;",
  console_sql:
    "SELECT uuid, point IS NULL AS point_missing FROM uranus.venue WHERE uuid = '00000000-0000-4000-8000-000000000020' LIMIT 50;",
  parameters: { entity_key: '00000000-0000-4000-8000-000000000020', diagnostic_limit: 50 },
  explanation: 'point IS NULL OR ST_IsEmpty(point)',
  columns: ['uuid', 'point_missing'],
  last_seen_at: '2026-09-14T12:00:00Z',
}
export const diagnosticResult: SqlDiagnosticResult = {
  recipe_id: 'venue_missing_location',
  columns: ['uuid', 'point_missing'],
  rows: [{ uuid: '00000000-0000-4000-8000-000000000020', point_missing: true }],
  row_count: 1,
  duration_ms: 1.5,
  observed_at: '2026-09-20T13:02:00Z',
  evaluation: {
    engine: 'Python',
    matched: true,
    message: 'Aktueller Datenstand erfüllt die Regel.',
    checks: [
      {
        label: 'point IS NULL OR ST_IsEmpty(point)',
        value: true,
        left: null,
        operator: null,
        right: null,
      },
    ],
  },
}
