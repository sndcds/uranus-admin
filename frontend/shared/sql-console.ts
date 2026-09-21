import { z } from './zod'

export const consolePath = '/api/admin/api/v1/sql-console/ws'
const base = { v: z.literal(1), request_id: z.uuid() }
const cell = z.union([
  z.string(),
  z.number().finite(),
  z.boolean(),
  z.null(),
  z.object({ value: z.string(), truncated: z.literal(true) }).strict(),
])
export const consoleClientSchema = z.discriminatedUnion('type', [
  z
    .object({
      ...base,
      type: z.literal('execute'),
      sql: z.string().min(1).max(32768),
      params: z.object({}).strict(),
      row_limit: z.number().int().min(1).max(500).optional(),
    })
    .strict(),
  z.object({ ...base, type: z.literal('cancel') }).strict(),
  z.object({ ...base, type: z.literal('ack'), batch: z.number().int().min(1).max(500) }).strict(),
])
export const consoleErrorCodes = [
  'invalid_sql',
  'query_only',
  'query_too_complex',
  'function_denied',
  'permission_denied',
  'syntax_error',
  'timeout',
  'result_too_large',
  'unavailable',
  'unsafe_identity',
  'busy',
  'protocol_error',
] as const
export const consoleServerSchema = z.discriminatedUnion('type', [
  z.object({ ...base, type: z.literal('started') }).strict(),
  z
    .object({ ...base, type: z.literal('columns'), columns: z.array(z.string().max(128)).max(128) })
    .strict(),
  z
    .object({
      ...base,
      type: z.literal('rows'),
      batch: z.number().int().min(1).max(500),
      rows: z.array(z.record(z.string(), cell)).max(25),
    })
    .strict(),
  z
    .object({
      ...base,
      type: z.literal('complete'),
      row_count: z.number().int().min(0).max(500),
      truncated: z.boolean(),
      duration_ms: z.number().nonnegative(),
    })
    .strict(),
  z
    .object({ ...base, type: z.literal('cancelled'), duration_ms: z.number().nonnegative() })
    .strict(),
  z
    .object({
      ...base,
      type: z.literal('error'),
      code: z.enum(consoleErrorCodes),
      position: z.number().int().positive().optional(),
      duration_ms: z.number().nonnegative().optional(),
    })
    .strict(),
])
export type ConsoleClientMessage = z.infer<typeof consoleClientSchema>
export type ConsoleRow = Record<string, z.infer<typeof cell>>
export const consoleErrorMessages: Record<(typeof consoleErrorCodes)[number], string> = {
  invalid_sql: 'SQL darf höchstens 32 KiB enthalten.',
  query_only:
    'Nur eine lesende SELECT-Abfrage ist erlaubt. Freie Bind-Parameter sind nicht verfügbar.',
  query_too_complex: 'Die Abfrage ist zu komplex.',
  function_denied: 'Diese Funktion ist in der READ-ONLY Console nicht erlaubt.',
  permission_denied:
    'Kein Zugriff auf dieses Objekt. Verwenden Sie die freigegebenen uranus_console-Views.',
  syntax_error: 'SQL-Syntax oder Objektname ungültig.',
  timeout: 'Zeitlimit erreicht. Die Datenbankabfrage wurde abgebrochen.',
  result_too_large: 'Das Ergebnis überschreitet die zulässige Größe.',
  unavailable: 'Die SQL Console ist derzeit nicht verfügbar.',
  unsafe_identity: 'Die Console-Datenbankverbindung erfüllt die Sicherheitsgrenze nicht.',
  busy: 'Die SQL Console ist ausgelastet. Bitte erneut versuchen.',
  protocol_error: 'Die SQL-Verbindung wurde wegen eines Protokollfehlers beendet.',
}
