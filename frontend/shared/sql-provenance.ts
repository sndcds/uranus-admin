import { z } from './zod'
import views from './provenance-views.json' with { type: 'json' }
export type ProvenanceView = keyof typeof views
export const provenanceViews = views
const value = z.union([z.string().max(16384), z.number().finite(), z.boolean()])
export const provenanceParamsSchema = z
  .record(z.string().max(64), value)
  .refine((v) => Object.keys(v).length <= 30)
export type ProvenanceParams = z.infer<typeof provenanceParamsSchema>
export function validProvenanceParams(view: string, input: unknown) {
  if (!Object.hasOwn(views, view)) return null
  const parsed = provenanceParamsSchema.safeParse(input)
  if (
    !parsed.success ||
    Object.keys(parsed.data).some(
      (key) => !(views[view as ProvenanceView] as string[]).includes(key),
    )
  )
    return null
  return parsed.data
}
const forbidden = new Set([
  'password_hash',
  'api_import_token',
  'activate_token',
  'accept_token',
  'password_reset_token',
  'session_token',
  'smtp_password',
  'database_url',
  'metadata',
  'payload',
  'snapshot',
  'body_html',
  'body_text',
])
const column = z
  .string()
  .max(100)
  .regex(/^[a-zA-Z_][a-zA-Z_0-9]*$/)
  .refine((name) => !forbidden.has(name))
const scalar = z.union([z.string().max(16384), z.number().finite(), z.boolean(), z.null()])
export const provenanceSourceSchema = z
  .object({
    id: z.string().max(150),
    title: z.string().max(300),
    datasource: z.enum(['uranus', 'admin']),
    description: z.string().max(2000),
    sql: z.string().max(100000),
    copy_sql: z.string().max(200000).nullable(),
    parameters: z.record(z.string().max(100), z.json()),
    columns: z.array(column).max(100),
    executable: z.boolean(),
    readonly: z.literal(true),
    implementation_ref: z.string().max(200),
    dependencies: z.array(z.string().max(1000)),
  })
  .strict()
export const provenanceDefinitionSchema = z
  .object({
    view_id: z.string(),
    title: z.string(),
    endpoint: z.string(),
    sources: z.array(provenanceSourceSchema).max(100),
    post_processing: z.array(z.string()),
    notes: z.array(z.string()),
    observed_at: z.iso.datetime({ offset: true }),
    parameters: provenanceParamsSchema,
  })
  .strict()
export const provenanceResultSchema = z
  .object({
    source_id: z.string(),
    datasource: z.enum(['uranus', 'admin']),
    columns: z.array(column).max(100),
    rows: z.array(z.record(column, scalar)).max(100),
    row_count: z.number().int().min(0).max(100),
    duration_ms: z.number().nonnegative(),
    observed_at: z.iso.datetime({ offset: true }),
    truncated: z.boolean(),
  })
  .strict()
  .refine(
    (result) =>
      result.row_count === result.rows.length &&
      result.rows.every(
        (row) =>
          Object.keys(row).length === result.columns.length &&
          result.columns.every((column) => Object.hasOwn(row, column)),
      ),
  )
export type ProvenanceDefinition = z.infer<typeof provenanceDefinitionSchema>
export type ProvenanceSource = z.infer<typeof provenanceSourceSchema>
export type ProvenanceResult = z.infer<typeof provenanceResultSchema>
