import { z } from 'zod'

// Explicit runtime-checked contract from docs/openapi.json (FastAPI 0.1.0).
// Missing optional metrics stay undefined; they are never replaced with mock numbers.
const count = z.number().int().nonnegative()
const timestamp = z.string().datetime({ offset: true })
export const periodSchema = z.enum(['today', '24h', '7d'])
export const severitySchema = z.enum(['error', 'warning', 'info'])
export const statusSchema = z.enum(['open', 'reviewed', 'ignored', 'resolved'])
export const summarySchema = z.object({
  period: periodSchema,
  from_at: timestamp,
  to_at: timestamp,
  admin_timezone: z.string(),
  source_timestamp_timezone: z.string(),
  new_records: z.object({
    total: count,
    organizations: count,
    venues: count,
    spaces: count,
    events: count,
    event_dates: count,
    users: count,
    partner_requests: count,
    team_memberships: count,
    images: count,
  }),
  images_without_created_at: count,
  urgent_findings: count,
  quality: z.object({
    total: count,
    warnings: count,
    errors: count.optional(),
    info: count.optional(),
    rules: z.array(z.string()).optional(),
    mode: z.literal('live').optional(),
  }),
  check_status: z.null().optional(),
})
export const findingSchema = z.object({
  id: z.string(),
  rule: z.string(),
  severity: severitySchema,
  priority: z.number().int().min(1).max(6),
  entity_type: z.string(),
  entity_key: z.string().min(1).max(1024),
  entity_id: z.uuid().nullable().optional(),
  entity_name: z.string(),
  organization_id: z.uuid(),
  organization_name: z.string(),
  field: z.string(),
  message: z.string(),
  address: z.object({
    street: z.string().nullable().optional(),
    house_number: z.string().nullable().optional(),
    postal_code: z.string().nullable().optional(),
    city: z.string().nullable().optional(),
    country: z.string().nullable().optional(),
  }),
  status: statusSchema.optional(),
  first_seen_at: timestamp.nullable().optional(),
  last_seen_at: timestamp,
  resolved_at: timestamp.nullable().optional(),
  upcoming_event_date_count: count,
  upcoming_published_event_date_count: count,
  soon_published_event_date_count: count,
})
export const findingPageSchema = z.object({
  items: z.array(findingSchema),
  pagination: z.object({
    page: count.min(1),
    page_size: count.min(1).max(100),
    total: count,
    pages: count,
  }),
  observed_at: timestamp,
  mode: z.literal('live').optional(),
})
export const healthSchema = z.object({ status: z.literal('ok').optional() })
export const errorSchema = z.object({ error: z.object({ code: z.string(), message: z.string() }) })
export type Period = z.infer<typeof periodSchema>
export type Severity = z.infer<typeof severitySchema>
export type Finding = z.infer<typeof findingSchema>
export type FindingPage = z.infer<typeof findingPageSchema>
export type DashboardSummary = z.infer<typeof summarySchema>

export const filtersSchema = z.object({
  severity: severitySchema.optional(),
  entity_type: z.string().max(64).optional(),
  rule: z.string().max(100).optional(),
  organization_id: z.uuid().optional(),
  status: statusSchema.optional(),
  page: z.coerce.number().int().min(1).max(100000).default(1),
  page_size: z.coerce.number().int().min(1).max(100).default(50),
})
export type FindingFilters = z.infer<typeof filtersSchema>

// Own API codes only. Messages are validated but replaced with local safe text.
export const adminErrorStatuses = {
  authentication_required: 401,
  invalid_credentials: 401,
  permission_denied: 403,
  invalid_input: 422,
  internal_error: 500,
  admin_auth_unconfigured: 503,
  source_timezone_unconfigured: 503,
  database_unavailable: 503,
  admin_storage_unconfigured: 503,
  check_run_conflict: 409,
  finding_not_found: 404,
} as const
export const adminErrorSchema = z.object({
  error: z.object({
    code: z.enum(Object.keys(adminErrorStatuses) as [keyof typeof adminErrorStatuses, ...Array<keyof typeof adminErrorStatuses>]),
    message: z.string().min(1).max(1024),
  }).strict(),
}).strict()
