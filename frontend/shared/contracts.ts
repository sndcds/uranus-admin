import { z } from './zod'

// Explicit runtime-checked contract from docs/openapi.json (FastAPI 0.1.0).
// Missing optional metrics stay undefined; they are never replaced with mock numbers.
const count = z.number().int().nonnegative()
const timestamp = z.string().datetime({ offset: true })
export const periodSchema = z.enum(['today', '24h', '7d'])
export const severitySchema = z.enum(['error', 'warning', 'info'])
export const statusSchema = z.enum([
  'open',
  'in_progress',
  'snoozed',
  'exception',
  'reviewed',
  'ignored',
  'resolved',
])
const dashboardCheckRunSchema = z.object({
  id: z.uuid(),
  status: z.enum(['queued', 'running', 'success', 'failed']),
  started_at: timestamp,
  finished_at: timestamp.nullable(),
  finding_count: count,
  rule_count: count,
})
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
    mode: z.enum(['live', 'persisted']).optional(),
  }),
  check_status: z
    .object({
      latest_run: dashboardCheckRunSchema.nullable(),
      last_successful_run: dashboardCheckRunSchema.nullable(),
    })
    .nullable()
    .optional(),
})
export const actionSchema = z
  .object({
    type: z.literal('view'),
    route: z.enum(['activity', 'partner_requests', 'team_invitations', 'user_activation']),
    entity_type: z
      .enum([
        'organization',
        'venue',
        'space',
        'event',
        'event_date',
        'user',
        'partner_request',
        'team_membership',
        'image',
      ])
      .nullable()
      .optional(),
    entity_key: z.string().min(1).max(1024),
    href: z.string(),
  })
  .refine((action) => {
    if (action.route === 'activity' && !action.entity_type) return false
    const path = action.route === 'activity' ? '/activity' : `/queues/${action.route}`
    const key = encodeURIComponent(action.entity_key).replace(
      /[!'()*]/g,
      (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`,
    )
    const suffix = action.route === 'activity' ? `&entity_type=${action.entity_type}` : ''
    return action.href === `${path}?entity_key=${key}${suffix}`
  }, 'Invalid internal action target')

export const findingSchema = z.object({
  id: z.string(),
  rule: z.string(),
  severity: severitySchema,
  priority: z.number().int().min(1).max(6),
  priority_score: count,
  priority_reasons: z.array(z.string()),
  entity_type: z.string(),
  entity_key: z.string().min(1).max(1024),
  entity_id: z.uuid().nullable().optional(),
  entity_name: z.string(),
  organization_id: z.uuid().nullable(),
  organization_name: z.string().nullable(),
  field: z.string(),
  message: z.string(),
  action: actionSchema.nullable().optional(),
  address: z.object({
    street: z.string().nullable().optional(),
    house_number: z.string().nullable().optional(),
    postal_code: z.string().nullable().optional(),
    city: z.string().nullable().optional(),
    country: z.string().nullable().optional(),
  }),
  status: statusSchema.optional(),
  assigned_to: z.uuid().nullable().optional(),
  reviewed_by: z.uuid().nullable().optional(),
  reviewed_subject: z.string().nullable().optional(),
  reviewed_at: timestamp.nullable().optional(),
  snoozed_until: timestamp.nullable().optional(),
  comment: z.string().nullable().optional(),
  exception_reason: z.string().nullable().optional(),
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
  mode: z.enum(['live', 'persisted']).optional(),
})
export const healthSchema = z.object({ status: z.literal('ok').optional() })
export const errorSchema = z.object({ error: z.object({ code: z.string(), message: z.string() }) })
export type Period = z.infer<typeof periodSchema>
export type Severity = z.infer<typeof severitySchema>
export type Finding = z.infer<typeof findingSchema>
export type FindingPage = z.infer<typeof findingPageSchema>
export type DashboardSummary = z.infer<typeof summarySchema>

export const filtersSchema = z.object({
  mode: z.enum(['live', 'persisted']).default('persisted'),
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
  admin_access_denied: 403,
  csrf_rejected: 403,
  login_rate_limited: 429,
  request_too_large: 413,
  auth_storage_unavailable: 503,
  invalid_input: 422,
  internal_error: 500,
  admin_auth_unconfigured: 503,
  source_timezone_unconfigured: 503,
  database_unavailable: 503,
  admin_storage_unconfigured: 503,
  check_run_conflict: 409,
  check_run_not_found: 404,
  finding_not_found: 404,
  mark_not_found: 404,
  record_not_found: 404,
  mark_conflict: 409,
} as const
export const adminErrorSchema = z
  .object({
    error: z
      .object({
        code: z.enum(
          Object.keys(adminErrorStatuses) as [
            keyof typeof adminErrorStatuses,
            ...Array<keyof typeof adminErrorStatuses>,
          ],
        ),
        message: z.string().min(1).max(1024),
      })
      .strict(),
  })
  .strict()

export const entityTypeSchema = z.enum([
  'organization',
  'venue',
  'space',
  'event',
  'event_date',
  'user',
  'partner_request',
  'team_membership',
  'image',
])
// Accept earlier thumbnail formats during deployment; new URLs omit cropping ratios.
export const activityImageUrlSchema = z.union([
  z
    .string()
    .regex(
      /^https:\/\/api\.kulturbytes\.de\/api\/image\/[0-9a-f-]{36}\?(?:width=320(?:&ratio=16%3A9)?|width=160&ratio=1%3A1)$/i,
    ),
  z.string().regex(/^https:\/\/api\.kulturbytes\.de\/api\/user\/[0-9a-f-]{36}\/avatar\/128$/i),
])
export const activityLocationSchema = z
  .object({
    latitude: z.number().finite().min(-90).max(90),
    longitude: z.number().finite().min(-180).max(180),
  })
  .strict()

export const activityPageSchema = z.object({
  items: z.array(
    z.object({
      entity_type: entityTypeSchema,
      entity_key: z.string(),
      entity_name: z.string(),
      organization_id: z.uuid().nullable(),
      organization_name: z.string().nullable(),
      created_at: timestamp.nullable(),
      status: z.string().nullable(),
      action: actionSchema.nullable(),
      image_url: activityImageUrlSchema.nullable().optional(),
      public_url: z
        .string()
        .regex(
          /^https:\/\/kulturbytes\.de\/de\/(?:ort\/[a-z0-9-]+|veranstaltung\/[0-9a-f-]{36}\/[0-9a-f-]{36})$/i,
        )
        .nullable()
        .optional(),
      subtitle: z.string().nullable().optional(),
      address: z.string().nullable().optional(),
      email: z.string().nullable().optional(),
      location: activityLocationSchema.nullable().optional(),
    }),
  ),
  pagination: findingPageSchema.shape.pagination,
  observed_at: timestamp,
  from_at: timestamp.nullable(),
  to_at: timestamp.nullable(),
  timestamp_state: z.enum(['known', 'unknown']),
  unknown_timestamp_count: count,
})
export type ActivityPage = z.infer<typeof activityPageSchema>

export const queueKindSchema = z.enum(['partner_requests', 'team_invitations', 'user_activation'])
export const queuePageSchema = z.object({
  kind: queueKindSchema,
  items: z.array(
    z.object({
      entity_key: z.string(),
      organization_id: z.uuid().nullable(),
      organization_name: z.string().nullable(),
      from_organization_id: z.uuid().nullable(),
      from_organization_name: z.string().nullable(),
      to_organization_id: z.uuid().nullable(),
      to_organization_name: z.string().nullable(),
      user_id: z.uuid(),
      user_name: z.string().nullable(),
      status: z.string(),
      created_at: timestamp,
      invited_at: timestamp.nullable(),
      has_joined: z.boolean().nullable(),
      age_days: count.nullable(),
      age_basis: z.enum(['created_at', 'invited_at']),
      checks: z.array(z.string()),
      action: actionSchema,
    }),
  ),
  pagination: findingPageSchema.shape.pagination,
  observed_at: timestamp,
})
export type QueuePage = z.infer<typeof queuePageSchema>
export const checkRunSchema = z.object({
  id: z.uuid(),
  started_at: timestamp,
  finished_at: timestamp.nullable(),
  status: z.enum(['queued', 'running', 'success', 'failed']),
  rule_count: count,
  finding_count: count,
  error_message: z.string().nullable(),
  rule_results: z.record(z.string(), z.unknown()),
})
export const checkRunPageSchema = z.object({
  items: z.array(checkRunSchema),
  pagination: findingPageSchema.shape.pagination,
})
export const reviewUpdateSchema = z
  .object({
    finding_id: z.string().min(1).max(8192),
    status: z.enum(['open', 'in_progress', 'snoozed', 'exception']),
    assigned_to: z.uuid().nullable().optional(),
    snoozed_until: timestamp.nullable().optional(),
    comment: z.string().max(4000).nullable().optional(),
    exception_reason: z.string().max(2000).nullable().optional(),
  })
  .strict()
  .refine((value) => value.status !== 'snoozed' || !!value.snoozed_until)
  .refine((value) => value.status !== 'exception' || !!value.exception_reason?.trim())
export type ReviewUpdate = z.infer<typeof reviewUpdateSchema>

export const markEntityTypeSchema = z.enum([
  ...entityTypeSchema.options,
  'event_link',
  'license',
  'image_link',
])
export const markReasonSchema = z.enum([
  'questionable_content',
  'low_quality',
  'incorrect',
  'incomplete',
  'outdated',
  'duplicate',
  'spam',
  'unsuitable',
  'rights_privacy',
  'technical',
  'other',
])
export const markStatusSchema = z.enum(['open', 'in_progress', 'done'])
export const markUrgencySchema = z.enum(['normal', 'high', 'urgent'])
const markFields = {
  reasons: z
    .array(markReasonSchema)
    .min(1)
    .max(11)
    .refine((v) => new Set(v).size === v.length),
  reason_detail: z.string().trim().min(1).max(2000).nullable().optional(),
  urgency: markUrgencySchema,
}
const hasExplanation = (v: { reasons: string[]; reason_detail?: string | null }) =>
  !v.reasons.includes('other') || !!v.reason_detail?.trim()
export const markCreateSchema = z
  .object({
    ...markFields,
    entity_type: markEntityTypeSchema,
    entity_key: z.string().trim().min(1).max(1024),
    note: z.string().trim().min(1).max(4000).nullable().optional(),
  })
  .strict()
  .refine(hasExplanation)
export const markUpdateSchema = z
  .object({
    ...markFields,
    version: z.number().int().min(1),
    status: markStatusSchema,
    note: z.string().trim().min(1).max(4000).nullable().optional(),
  })
  .strict()
  .refine(hasExplanation)
export const markSchema = z.object({
  id: z.uuid(),
  entity_type: markEntityTypeSchema,
  entity_key: z.string(),
  entity_name: z.string(),
  reasons: z.array(markReasonSchema),
  reason_detail: z.string().nullable(),
  urgency: markUrgencySchema,
  status: markStatusSchema,
  version: z.number().int().min(1),
  created_at: timestamp,
  created_by: z.string(),
  updated_at: timestamp,
  completed_at: timestamp.nullable(),
  completed_by: z.string().nullable(),
})
export const markEventSchema = z.object({
  id: z.uuid(),
  version: z.number().int().min(1),
  kind: z.enum(['created', 'updated', 'completed', 'reopened']),
  author: z.string(),
  created_at: timestamp,
  note: z.string().nullable(),
  status: markStatusSchema,
  reasons: z.array(markReasonSchema),
  reason_detail: z.string().nullable(),
  urgency: markUrgencySchema,
})
export const markDetailSchema = markSchema.extend({ events: z.array(markEventSchema) })
export const markPageSchema = z.object({
  items: z.array(markSchema),
  pagination: findingPageSchema.shape.pagination,
})
export type Mark = z.infer<typeof markSchema>
export type MarkDetail = z.infer<typeof markDetailSchema>
export type MarkPage = z.infer<typeof markPageSchema>
export type MarkCreate = z.infer<typeof markCreateSchema>
export type MarkUpdate = z.infer<typeof markUpdateSchema>

// Credentials are request-only; session responses never contain tokens or passwords.
export const loginSchema = z
  .object({
    login: z.string().trim().min(1).max(254),
    password: z.string().min(1).max(1024),
  })
  .strict()
export const sessionSchema = z
  .object({
    subject: z.string().min(1).max(128),
    system_admin: z.boolean(),
  })
  .strict()
export const logoutSchema = z.object({ status: z.literal('ok') }).strict()
export type AdminSession = z.infer<typeof sessionSchema>

export const graphEntityTypeSchema = z.enum([
  'organization',
  'venue',
  'space',
  'event',
  'event_date',
  'user',
])
export const graphRelationTypeSchema = z.enum([
  'organization_has_venue',
  'venue_has_space',
  'organization_has_event',
  'event_has_date',
  'event_uses_venue',
  'event_uses_space',
  'event_date_uses_venue',
  'event_date_uses_space',
  'user_member_of_organization',
  'user_invited_to_organization',
  'organization_partner_request',
  'organization_partner_of',
])
export const graphNodeSchema = z
  .object({
    id: z.string(),
    type: graphEntityTypeSchema,
    key: z.uuid(),
    label: z.string(),
    subtitle: z.string().nullable(),
    status: z.string().nullable(),
    public_url: activityPageSchema.shape.items.element.shape.public_url,
    admin_url: z.string().nullable(),
  })
  .refine(
    (n) =>
      n.id === `${n.type}:${n.key}` &&
      (n.admin_url === null ||
        n.admin_url === `/activity?entity_key=${n.key}&entity_type=${n.type}`),
    'Invalid graph identity or target',
  )
export const graphEdgeSchema = z.object({
  id: z.string(),
  source: z.string(),
  target: z.string(),
  type: graphRelationTypeSchema,
  label: z.string(),
  direction: z.enum(['directed', 'undirected']),
})
export const graphResponseSchema = z
  .object({
    root: z.object({ type: graphEntityTypeSchema, key: z.uuid() }),
    nodes: z.array(graphNodeSchema).max(100),
    edges: z.array(graphEdgeSchema).max(200),
    truncated: z.boolean(),
    max_nodes: z.number().int().positive().max(100),
    max_edges: z.number().int().positive().max(200),
  })
  .refine((g) => {
    const ids = new Set(g.nodes.map((n) => n.id))
    return (
      ids.size === g.nodes.length &&
      ids.has(`${g.root.type}:${g.root.key}`) &&
      new Set(g.edges.map((e) => e.id)).size === g.edges.length &&
      g.edges.every((e) => ids.has(e.source) && ids.has(e.target))
    )
  }, 'Invalid graph endpoints')
export const graphSearchResponseSchema = z.object({ items: z.array(graphNodeSchema).max(20) })
export type GraphEntityType = z.infer<typeof graphEntityTypeSchema>
export type GraphRelationType = z.infer<typeof graphRelationTypeSchema>
export type GraphNode = z.infer<typeof graphNodeSchema>
export type GraphEdge = z.infer<typeof graphEdgeSchema>
export type GraphResponse = z.infer<typeof graphResponseSchema>

export const statisticsPeriodSchema = z.enum(['24h', '7d', '30d', '90d', 'custom'])
export const statisticsIntervalSchema = z.enum(['15m', '1h', '6h', '1d'])
export const statisticsEntitySchema = z.enum([
  'user',
  'organization',
  'event',
  'venue',
  'space',
  'partner_request',
  'team_invitation',
])
export const entityStatisticsPointSchema = z
  .object({
    start_at: timestamp,
    end_at: timestamp,
    count,
  })
  .refine((point) => Date.parse(point.start_at) < Date.parse(point.end_at), 'Invalid bucket')
export const entityStatisticsSeriesSchema = z
  .object({
    entity_type: statisticsEntitySchema,
    label: z.string(),
    total: count,
    previous_total: count.nullable(),
    points: z.array(entityStatisticsPointSchema).min(1).max(500),
  })
  .refine(
    (series) => series.total === series.points.reduce((sum, point) => sum + point.count, 0),
    'Invalid total',
  )
export const entityStatisticsResponseSchema = z
  .object({
    period: statisticsPeriodSchema,
    from_at: timestamp,
    to_at: timestamp,
    timezone: z.string().refine((zone) => {
      try {
        new Intl.DateTimeFormat('de', { timeZone: zone })
        return true
      } catch {
        return false
      }
    }),
    interval: statisticsIntervalSchema,
    observed_at: timestamp,
    previous_from_at: timestamp.nullable(),
    previous_to_at: timestamp.nullable(),
    series: z.array(entityStatisticsSeriesSchema).length(7),
    recent: z
      .array(
        z.object({
          entity_type: statisticsEntitySchema,
          entity_key: z.string(),
          entity_name: z.string(),
          organization_name: z.string().nullable(),
          created_at: timestamp,
          action: actionSchema,
        }),
      )
      .max(7),
  })
  .refine((data) => {
    const start = Date.parse(data.from_at),
      end = Date.parse(data.to_at)
    const reference = data.series[0]!.points
    const comparing = data.previous_from_at !== null && data.previous_to_at !== null
    return (
      start < end &&
      end - start <= 365 * 86400000 &&
      new Set(data.series.map((s) => s.entity_type)).size === 7 &&
      (comparing || (data.previous_from_at === null && data.previous_to_at === null)) &&
      (!comparing ||
        (Date.parse(data.previous_to_at!) === start &&
          start - Date.parse(data.previous_from_at!) === end - start)) &&
      data.series.every(
        (series) =>
          (comparing ? series.previous_total !== null : series.previous_total === null) &&
          series.points.length === reference.length &&
          series.points.every(
            (point, i) =>
              Date.parse(point.start_at) ===
                (i ? Date.parse(series.points[i - 1]!.end_at) : start) &&
              Date.parse(point.start_at) === Date.parse(reference[i]!.start_at) &&
              Date.parse(point.end_at) === Date.parse(reference[i]!.end_at) &&
              (i !== series.points.length - 1 || Date.parse(point.end_at) === end),
          ),
      ) &&
      data.recent.every(
        (item) => Date.parse(item.created_at) >= start && Date.parse(item.created_at) < end,
      )
    )
  }, 'Inconsistent statistics range or series')
export type StatisticsEntity = z.infer<typeof statisticsEntitySchema>
export type EntityStatistics = z.infer<typeof entityStatisticsResponseSchema>
export type StatisticsSeries = z.infer<typeof entityStatisticsSeriesSchema>
