import { z } from './zod'

// Explicit runtime-checked contract from docs/openapi.json (FastAPI 0.1.0).
// Missing optional metrics stay undefined; they are never replaced with mock numbers.
const count = z.number().int().nonnegative()
const timestamp = z.string().datetime({ offset: true })
export const sharedPeriodSchema = z.enum(['today', '24h', '7d', '30d', '90d'])
export type SharedPeriod = z.infer<typeof sharedPeriodSchema>
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
  geo_scope_id: z.uuid().nullable().optional(),
  new_record_scopes: z.record(z.string(), z.enum(['geo', 'global'])).optional(),
  scoped_new_records_total: count.nullable().optional(),
  global_new_records_total: count.nullable().optional(),
  images_without_created_at: count,
  urgent_findings: count,
  quality: z.object({
    total: count,
    warnings: count,
    errors: count.optional(),
    info: count.optional(),
    rules: z.array(z.string()).optional(),
    rule_counts: z.record(z.string(), count).optional(),
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
    const sections: Record<string, string> = {
      event: 'events',
      venue: 'venues',
      space: 'spaces',
      organization: 'organizations',
      user: 'users',
      image: 'images',
    }
    if (
      action.route === 'activity' &&
      action.entity_type &&
      sections[action.entity_type] &&
      z.uuid().safeParse(action.entity_key).success &&
      action.href === `/${sections[action.entity_type]}/${action.entity_key.toLowerCase()}`
    )
      return true
    const path = action.route === 'activity' ? '/activity' : `/queues/${action.route}`
    const key = encodeURIComponent(action.entity_key).replace(
      /[!'()*]/g,
      (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`,
    )
    const suffix = action.route === 'activity' ? `&entity_type=${action.entity_type}` : ''
    return action.href === `${path}?entity_key=${key}${suffix}`
  }, 'Invalid internal action target')

// Accept earlier thumbnail formats during deployment; new URLs omit cropping ratios.
export const activityImageUrlSchema = z.union([
  z
    .string()
    .regex(
      /^https:\/\/api\.kulturbytes\.de\/api\/image\/[0-9a-f-]{36}\?(?:width=320(?:&ratio=16%3A9)?|width=160&ratio=1%3A1)$/i,
    ),
  z.string().regex(/^https:\/\/api\.kulturbytes\.de\/api\/user\/[0-9a-f-]{36}\/avatar\/128$/i),
])

export const findingSchema = z.object({
  sql_diagnostic_available: z.boolean().optional().default(false),
  location_suggestion_request_id: z.uuid().nullable().optional(),
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
  image_url: activityImageUrlSchema.nullable().optional(),
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
export const cursorPaginationSchema = z.object({
  page_size: count,
  next_cursor: z.string().nullable(),
  has_more: z.boolean(),
})
export const findingPageSchema = z.object({
  cursor_pagination: cursorPaginationSchema.nullable().optional(),
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
  geo_scope_id: z.uuid().optional(),
  mode: z.enum(['live', 'persisted']).default('persisted'),
  severity: severitySchema.optional(),
  entity_type: z.string().max(64).optional(),
  entity_key: z.string().min(1).max(1024).optional(),
  rule: z.string().max(100).optional(),
  organization_id: z.uuid().optional(),
  status: statusSchema.optional(),
  active_only: z
    .union([z.boolean(), z.enum(['true', 'false']).transform((value) => value === 'true')])
    .default(false),
  page: z.coerce.number().int().min(1).max(100000).default(1),
  page_size: z.coerce.number().int().min(1).max(100).default(50),
})
export type FindingFilters = z.infer<typeof filtersSchema>

export const adminOptionSchema = z
  .object({ id: z.uuid(), login: z.string().min(1).max(320) })
  .strict()
export const adminOptionPageSchema = z
  .object({ items: z.array(adminOptionSchema).max(200), admin_timezone: z.string().min(1) })
  .strict()
export const assignmentStatusSchema = z.enum(['open', 'in_progress', 'done', 'cancelled'])
export const assignmentWorkflowTypeSchema = z.enum(['geocode_request', 'notification_delivery'])
export const assignmentSchema = z
  .object({
    id: z.uuid(),
    finding_id: z.string().min(1).max(8192).nullable(),
    workflow_type: assignmentWorkflowTypeSchema.nullable(),
    workflow_key: z.string().min(1).max(1024).nullable(),
    entity_type: z.string().min(1).max(64),
    entity_key: z.string().min(1).max(1024),
    assigned_to: adminOptionSchema,
    assigned_by_subject: z.string().min(1).max(256),
    status: assignmentStatusSchema,
    due_at: timestamp.nullable(),
    snoozed_until: timestamp.nullable(),
    created_at: timestamp,
    updated_at: timestamp,
    completed_at: timestamp.nullable(),
    version: count.min(1),
  })
  .strict()
export const optionalAssignmentSchema = assignmentSchema.nullable()
export const assignmentLookupSchema = z
  .object({
    finding_id: z.string().min(1).max(8192).optional(),
    workflow_type: assignmentWorkflowTypeSchema.optional(),
    workflow_key: z.string().min(1).max(1024).optional(),
  })
  .strict()
  .refine(
    (value) =>
      (!!value.finding_id && !value.workflow_type && !value.workflow_key) ||
      (!value.finding_id && !!value.workflow_type && !!value.workflow_key),
  )
export const assignmentCreateSchema = z
  .object({
    finding_id: z.string().min(1).max(8192).optional(),
    workflow_type: assignmentWorkflowTypeSchema.optional(),
    workflow_key: z.string().min(1).max(1024).optional(),
    entity_type: z.string().min(1).max(64).optional(),
    entity_key: z.string().min(1).max(1024).optional(),
    assigned_to_admin_id: z.uuid(),
    status: z.enum(['open', 'in_progress']).default('open'),
    due_at: timestamp.nullable().optional(),
  })
  .strict()
  .refine(
    (value) =>
      !!value.finding_id !== !!value.workflow_type &&
      (!value.workflow_type ||
        (!!value.workflow_key && !!value.entity_type && !!value.entity_key)) &&
      (!value.finding_id || (!value.entity_type && !value.entity_key && !value.workflow_key)),
  )
export const assignmentUpdateSchema = z
  .object({
    version: count.min(1),
    assigned_to_admin_id: z.uuid().optional(),
    status: assignmentStatusSchema.optional(),
    due_at: timestamp.nullable().optional(),
    snoozed_until: timestamp.nullable().optional(),
  })
  .strict()
  .refine((value) => Object.keys(value).some((key) => key !== 'version'))
export type AdminOption = z.infer<typeof adminOptionSchema>
export type Assignment = z.infer<typeof assignmentSchema>
export type AssignmentStatus = z.infer<typeof assignmentStatusSchema>
export type AssignmentWorkflowType = z.infer<typeof assignmentWorkflowTypeSchema>
export type AssignmentCreate = z.infer<typeof assignmentCreateSchema>
export type AssignmentUpdate = z.infer<typeof assignmentUpdateSchema>

export const inboxKindSchema = z.enum([
  'assignment',
  'finding',
  'geocode_request',
  'notification_delivery',
])
export const inboxScopeSchema = z.enum(['all', 'mine', 'unassigned'])
export const inboxAttentionSchema = z.enum(['all', 'critical', 'due_today', 'overdue', 'snoozed'])
export const inboxFiltersSchema = z
  .object({
    scope: inboxScopeSchema.default('all'),
    attention: inboxAttentionSchema.default('all'),
    kind: inboxKindSchema.optional(),
    entity_type: z.string().min(1).max(64).optional(),
    page: z.coerce.number().int().min(1).max(100000).default(1),
    page_size: z.coerce.number().int().min(1).max(100).default(25),
  })
  .strict()
export const inboxHrefSchema = z
  .string()
  .max(4096)
  .refine((value) => {
    try {
      const url = new URL(value, 'https://admin.invalid')
      if (url.origin !== 'https://admin.invalid' || `${url.pathname}${url.search}` !== value)
        return false
      const uuid = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
      if (new RegExp(`^/(?:geocoding|notifications/deliveries)/${uuid}$`, 'i').test(url.pathname))
        return !url.search
      if (url.pathname !== '/findings') return false
      return (
        [...url.searchParams.keys()].sort().join(',') === 'entity_key,rule' &&
        !!url.searchParams.get('entity_key')
      )
    } catch {
      return false
    }
  })
export const inboxItemSchema = z
  .object({
    id: z.string().min(1).max(8192),
    kind: inboxKindSchema,
    title: z.string().min(1).max(500),
    summary: z.string().min(1).max(5000),
    entity_type: z.string().min(1).max(64),
    entity_key: z.string().min(1).max(1024),
    entity_name: z.string().min(1).max(500),
    organization_name: z.string().max(500).nullable(),
    entity_action: actionSchema.nullable(),
    severity: severitySchema.nullable(),
    status: z.string().min(1).max(64),
    workflow_status: z.string().max(64).nullable(),
    candidate_count: count.nullable(),
    occurred_at: timestamp,
    due_at: timestamp.nullable(),
    snoozed_until: timestamp.nullable(),
    finding_snoozed_until: timestamp.nullable(),
    is_overdue: z.boolean(),
    due_today: z.boolean(),
    assignment: assignmentSchema.nullable(),
    href: inboxHrefSchema,
  })
  .strict()
export const inboxPageSchema = z
  .object({
    items: z.array(inboxItemSchema).max(100),
    admin_timezone: z.string().min(1),
    counts: z
      .object({
        critical: count,
        mine: count,
        unassigned: count,
        due_today: count,
        overdue: count,
        snoozed: count,
      })
      .strict(),
    pagination: findingPageSchema.shape.pagination,
    observed_at: timestamp,
  })
  .strict()
export type InboxFilters = z.infer<typeof inboxFiltersSchema>
export type InboxPage = z.infer<typeof inboxPageSchema>

// Own API codes only. Messages are validated but replaced with local safe text.
export const adminErrorStatuses = {
  geocode_request_not_found: 404,
  geocode_retry_not_allowed: 409,
  geocode_no_longer_needed: 409,
  geo_scope_not_found: 404,
  geo_provider_unavailable: 503,
  geo_area_not_eligible: 422,
  geo_area_geometry_invalid: 422,
  notification_delivery_not_found: 404,
  notification_retry_not_allowed: 409,
  notification_retry_obsolete: 409,
  notification_retry_already_queued: 409,
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
  assignment_not_found: 404,
  assignment_task_not_found: 404,
  assignment_assignee_invalid: 422,
  assignment_task_invalid: 422,
  assignment_task_closed: 422,
  assignment_conflict: 409,
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
export const activityLocationSchema = z
  .object({
    latitude: z.number().finite().min(-90).max(90),
    longitude: z.number().finite().min(-180).max(180),
  })
  .strict()

export const activityPageSchema = z.object({
  cursor_pagination: cursorPaginationSchema.nullable().optional(),
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
      notice: z.string().nullable().optional(),
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
export const membershipStatusSchema = z.enum(['invited', 'joined', 'all'])
export type MembershipStatus = z.infer<typeof membershipStatusSchema>
export type QueueQuery = {
  organization_id?: string
  entity_key?: string
  status?: string
  membership_status?: MembershipStatus
  min_age_days?: string | number
  page?: string | number
  page_size?: string | number
}
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
  action: actionSchema.nullable().optional(),
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
        actionSchema.safeParse({
          type: 'view',
          route: 'activity',
          entity_type: n.type,
          entity_key: n.key,
          href: n.admin_url,
        }).success),
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
    scope: z.enum(['geo', 'global']).optional(),
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

export const entitySectionSchema = z.enum([
  'events',
  'venues',
  'spaces',
  'organizations',
  'users',
  'images',
])
export type EntitySection = z.infer<typeof entitySectionSchema>
export const entityFactsSchema = z.object({
  username: z.string().nullable(),
  description: z.string().nullable(),
  venue_name: z.string().nullable(),
  space_name: z.string().nullable(),
  event_dates: count.nullable(),
  venues: count.nullable(),
  spaces: count.nullable(),
  events: count.nullable(),
  memberships: count.nullable(),
  image_links: count.nullable(),
  orphan: z.boolean().nullable(),
})
export const entityRecordSchema = activityPageSchema.shape.items.element.extend({
  facts: entityFactsSchema,
  finding_count: count.nullable(),
  mark_count: count.nullable(),
})
export const entityPageSchema = z.object({
  items: z.array(entityRecordSchema),
  pagination: findingPageSchema.shape.pagination,
  observed_at: timestamp,
})
export const entityDetailSchema = z.object({
  item: entityRecordSchema,
  related: z.object({
    items: activityPageSchema.shape.items,
    pagination: findingPageSchema.shape.pagination,
  }),
  observed_at: timestamp,
})
export type EntityPage = z.infer<typeof entityPageSchema>
export type EntityDetail = z.infer<typeof entityDetailSchema>

export const timelineEntityTypeSchema = z.enum([
  'event',
  'organization',
  'venue',
  'space',
  'user',
  'image',
])
export const timelineKindSchema = z.enum([
  'source_created',
  'source_updated',
  'finding_detected',
  'finding_reviewed',
  'finding_reopened',
  'finding_resolved',
  'mark_created',
  'mark_updated',
  'mark_completed',
  'mark_reopened',
  'assignment_created',
  'assignment_updated',
  'assignment_snoozed',
  'assignment_unsnoozed',
  'assignment_completed',
  'assignment_reopened',
  'assignment_cancelled',
  'notification_delivery',
  'url_check',
  'geocode_request',
  'geocode_result',
  'team_invitation',
  'partner_request',
])
const timelineHrefSchema = z
  .string()
  .max(4096)
  .refine((value) => {
    try {
      const url = new URL(value, 'https://admin.invalid')
      if (`${url.pathname}${url.search}` !== value || url.origin !== 'https://admin.invalid')
        return false
      const uuid = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
      const detail = new RegExp(`^/(?:marks|geocoding)/${uuid}$`, 'i').test(url.pathname)
      const delivery = new RegExp(`^/notifications/deliveries/${uuid}$`, 'i').test(url.pathname)
      if (detail || delivery) return !url.search
      const keys = [...url.searchParams.keys()].sort()
      if (url.pathname === '/findings')
        return (
          JSON.stringify(keys) ===
            JSON.stringify(['entity_key', 'entity_type', 'mode', 'rule'].sort()) &&
          url.searchParams.get('mode') === 'persisted'
        )
      if (['/queues/team_invitations', '/queues/partner_requests'].includes(url.pathname))
        return JSON.stringify(keys) === JSON.stringify(['entity_key'])
      return false
    } catch {
      return false
    }
  }, 'Invalid timeline target')
export const timelineItemSchema = z.object({
  id: z.string().min(1).max(4096),
  kind: timelineKindSchema,
  occurred_at: timestamp,
  title: z.string().min(1).max(200),
  summary: z.string().max(5000).nullable(),
  actor: z.string().max(256).nullable(),
  href: timelineHrefSchema.nullable(),
  metadata: z.object({
    status: z.string().max(64).nullable(),
    severity: severitySchema.nullable(),
    rule: z.string().max(100).nullable(),
    field: z.string().max(200).nullable(),
    resource_id: z.string().max(8192).nullable(),
    generation: z.number().int().positive().nullable(),
    score: z.number().min(0).max(1).nullable(),
    http_status: z.number().int().min(100).max(599).nullable(),
  }),
})
export const timelinePageSchema = z.object({
  entity_type: timelineEntityTypeSchema,
  entity_key: z.uuid(),
  items: z.array(timelineItemSchema).max(50),
  cursor_pagination: cursorPaginationSchema,
  observed_at: timestamp,
})
export type TimelineEntityType = z.infer<typeof timelineEntityTypeSchema>
export type TimelineItem = z.infer<typeof timelineItemSchema>
export type TimelinePage = z.infer<typeof timelinePageSchema>

export const entitySearchTypeSchema = z.enum([
  'user',
  'organization',
  'venue',
  'space',
  'event',
  'image',
])
export type EntitySearchType = z.infer<typeof entitySearchTypeSchema>
export const entitySearchItemSchema = z
  .object({
    entity_type: entitySearchTypeSchema,
    entity_key: z.uuid(),
    label: z.string(),
    subtitle: z.string().nullable(),
    status: z.string().nullable(),
    action: actionSchema,
  })
  .refine(
    (item) =>
      item.action.route === 'activity' &&
      item.action.entity_type === item.entity_type &&
      item.action.entity_key === item.entity_key,
    'Mismatched search action',
  )
export type EntitySearchItem = z.infer<typeof entitySearchItemSchema>
export const entitySearchResponseSchema = z.object({
  items: z.array(entitySearchItemSchema).max(20),
})

export const searchFieldSchema = z.enum([
  'uuid',
  'username',
  'display_name',
  'email',
  'first_name',
  'last_name',
  'name',
  'contact_email',
  'city',
  'postal_code',
  'street',
  'house_number',
  'venue_name',
  'space_type',
  'title',
  'subtitle',
  'external_id',
  'file_name',
  'alt_text',
  'creator_name',
  'mime_type',
])
export const globalSearchItemSchema = z
  .object({
    entity_type: entitySearchTypeSchema,
    entity_key: z.uuid(),
    label: z.string(),
    subtitle: z.string().nullable(),
    action: actionSchema,
    matched_fields: z.array(searchFieldSchema).max(7),
  })
  .refine(
    (item) =>
      item.action.route === 'activity' &&
      item.action.entity_type === item.entity_type &&
      item.action.entity_key === item.entity_key,
  )
export const globalSearchResponseSchema = z
  .object({
    query: z.string().min(2).max(120),
    groups: z
      .array(
        z
          .object({
            entity_type: entitySearchTypeSchema,
            items: z.array(globalSearchItemSchema).min(1).max(10),
          })
          .refine((group) => group.items.every((item) => item.entity_type === group.entity_type)),
      )
      .max(6),
  })
  .refine((response) => {
    const types = response.groups.map((group) => group.entity_type)
    return (
      new Set(types).size === types.length &&
      types.every(
        (type, index) =>
          index === 0 ||
          entitySearchTypeSchema.options.indexOf(types[index - 1]!) <
            entitySearchTypeSchema.options.indexOf(type),
      )
    )
  })
export type GlobalSearchResponse = z.infer<typeof globalSearchResponseSchema>
export type GlobalSearchQuery = { q: string; limit_per_type?: number; types?: string }

export const temporalFilterSchema = z.enum(['upcoming', 'past'])
export type TemporalFilter = z.infer<typeof temporalFilterSchema>
export type EntitySearchQuery = {
  geo_scope_id?: string
  q: string
  entity_type: EntitySearchType
  period?: SharedPeriod
  temporal?: TemporalFilter
  organization_id?: string
  status?: string
  limit?: number
}

export const eventReleaseStatusSchema = z.enum([
  'released',
  'draft',
  'review',
  'cancelled',
  'deferred',
  'rescheduled',
])
export const eventContentPeriodSchema = sharedPeriodSchema.or(z.literal('all'))
const eventShare = z.number().min(0).max(100)
export const eventContentAssignmentCoverageSchema = z.object({
  events_with_assignment: count,
  events_without_assignment: count,
  coverage_percent: eventShare,
})
export const eventContentCoverageSchema = z.object({
  categories: eventContentAssignmentCoverageSchema,
  genres: eventContentAssignmentCoverageSchema,
  event_types: eventContentAssignmentCoverageSchema,
})
export const eventContentRankingItemSchema = z.object({
  id: z.string(),
  name: z.string(),
  event_count: count,
  event_share_percent: eventShare,
  rank: z.number().int().positive(),
  previous_rank: z.number().int().positive().nullable(),
  rank_delta: z.number().int().nullable(),
  previous_event_count: count.nullable(),
  count_delta: z.number().int().nullable(),
  previous_share_percent: eventShare.nullable(),
  share_delta_percentage_points: z.number().min(-100).max(100).nullable(),
})
export const eventContentRankingSchema = z.object({
  distinct_assignment_count: count,
  items: z.array(eventContentRankingItemSchema).max(10),
})
export const eventContentStatisticsSchema = z
  .object({
    period: eventContentPeriodSchema,
    from_at: timestamp.nullable(),
    to_at: timestamp.nullable(),
    timezone: z.string(),
    observed_at: timestamp,
    status: eventReleaseStatusSchema.nullable(),
    event_count: count,
    coverage: eventContentCoverageSchema,
    categories: eventContentRankingSchema,
    genres: eventContentRankingSchema,
    event_types: eventContentRankingSchema,
    comparison: z
      .object({
        from_at: timestamp,
        to_at: timestamp,
        event_count: count,
        coverage: eventContentCoverageSchema,
      })
      .nullable(),
  })
  .refine((data) => {
    const validCoverage = (coverage: EventContentCoverage, total: number) =>
      Object.values(coverage).every(
        (item) => item.events_with_assignment + item.events_without_assignment === total,
      )
    return (
      validCoverage(data.coverage, data.event_count) &&
      (data.period === 'all'
        ? data.from_at === null && data.to_at === null && data.comparison === null
        : data.from_at !== null &&
          data.to_at !== null &&
          Date.parse(data.from_at) <= Date.parse(data.to_at)) &&
      (!data.comparison || validCoverage(data.comparison.coverage, data.comparison.event_count)) &&
      [data.categories, data.genres, data.event_types].every(
        (ranking) =>
          ranking.items.length <= ranking.distinct_assignment_count &&
          new Set(ranking.items.map((item) => item.id)).size === ranking.items.length &&
          ranking.items.every(
            (item, i) => item.rank === i + 1 && item.event_count <= data.event_count,
          ),
      )
    )
  }, 'Inconsistent event content statistics')
export type EventContentCoverage = z.infer<typeof eventContentCoverageSchema>
export type EventContentRanking = z.infer<typeof eventContentRankingSchema>
export type EventContentStatistics = z.infer<typeof eventContentStatisticsSchema>
export type EventContentQuery = {
  geo_scope_id?: string
  period?: z.infer<typeof eventContentPeriodSchema>
  status?: z.infer<typeof eventReleaseStatusSchema>
  compare?: 'previous'
}

export const notificationStatusSchema = z.enum([
  'pending',
  'active',
  'resolved',
  'suppressed',
  'expired',
])
export const notificationTypeSchema = z.enum(['unpublished_upcoming_event', 'quality_finding'])
export const notificationDeliveryStatusSchema = z.enum([
  'queued',
  'sending',
  'sent',
  'failed',
  'permanent_failure',
  'cancelled',
])
export const notificationDeliveryKindSchema = z.enum([
  'initial',
  'reminder',
  'escalation',
  'digest',
  'test',
])
export const notificationLocaleSchema = z.enum(['de', 'da', 'en'])
export const notificationPayloadSchema = z.object({
  organization_name: z.string(),
  entity_name: z.string(),
  entity_type: z.string(),
  entity_key: z.string(),
  internal_action_path: z.string().nullable(),
  external_action_url: z.string().nullable(),
  event_status: z.enum(['draft', 'review']).nullable(),
  next_date: z.string().nullable(),
  days_until: z.number().int().nullable(),
  stage: count,
  episode: count,
  rule: z.string().nullable(),
  finding_id: z.string().nullable(),
  severity: z.string().nullable(),
  field: z.string().nullable(),
  relevance: z.array(z.string()),
  priority: z.enum(['urgent', 'important', 'improvement', 'internal']),
})
export const notificationSummarySchema = z.object({
  id: z.uuid(),
  notification_type: notificationTypeSchema,
  organization_id: z.uuid(),
  entity_type: z.string().nullable(),
  entity_key: z.string().nullable(),
  entity_name: z.string().nullable(),
  finding_id: z.string().nullable(),
  rule: z.string().nullable(),
  status: notificationStatusSchema,
  payload: notificationPayloadSchema,
  first_detected_at: timestamp,
  last_detected_at: timestamp,
  resolved_at: timestamp.nullable(),
  expired_at: timestamp.nullable(),
})
export const notificationDeliverySchema = z.object({
  id: z.uuid(),
  retry_of_delivery_id: z.uuid().nullable(),
  organization_id: z.uuid(),
  recipient: z.string(),
  locale: notificationLocaleSchema,
  delivery_kind: notificationDeliveryKindSchema,
  status: notificationDeliveryStatusSchema,
  subject: z.string().nullable(),
  message_fingerprint: z.string(),
  attempt_count: count,
  queued_at: timestamp.nullable(),
  sending_at: timestamp.nullable(),
  sent_at: timestamp.nullable(),
  next_attempt_at: timestamp.nullable(),
  last_error: z.string().nullable(),
  provider_message_id: z.string().nullable(),
})
export const notificationDetailSchema = notificationSummarySchema.extend({
  deliveries: z.array(notificationDeliverySchema),
  delivery_enabled: z.boolean(),
})
export const notificationDeliveryDetailSchema = notificationDeliverySchema.extend({
  retries: z.array(notificationDeliverySchema),
  notifications: z.array(notificationSummarySchema),
})
export const notificationPreviewSchema = z.object({
  subject: z.string(),
  text: z.string(),
  html: z.string(),
  locale: notificationLocaleSchema,
  notification_ids: z.array(z.uuid()),
  delivery_enabled: z.boolean(),
})
export const notificationPageSchema = z.object({
  items: z.array(notificationSummarySchema),
  pagination: z.object({ page: count, page_size: count, total: count, pages: count }),
  summary: z.object({
    active: count,
    queued: count,
    sent_today: count,
    failed: count,
    temporary_failed: count,
    permanent_failed: count,
  }),
  health: z.object({
    delivery_enabled: z.boolean(),
    source_capability: z.boolean(),
    config_issues: z.array(
      z.object({
        organization_id: z.uuid(),
        organization_name: z.string(),
        code: z.literal('invalid_config'),
      }),
    ),
  }),
})
export type NotificationStatus = z.infer<typeof notificationStatusSchema>
export type NotificationType = z.infer<typeof notificationTypeSchema>
export type NotificationDeliveryStatus = z.infer<typeof notificationDeliveryStatusSchema>
export type NotificationDeliveryKind = z.infer<typeof notificationDeliveryKindSchema>
export type NotificationSummary = z.infer<typeof notificationSummarySchema>
export type NotificationDetail = z.infer<typeof notificationDetailSchema>
export type NotificationDelivery = z.infer<typeof notificationDeliverySchema>
export type NotificationDeliveryDetail = z.infer<typeof notificationDeliveryDetailSchema>
export type NotificationPreview = z.infer<typeof notificationPreviewSchema>
export type NotificationPage = z.infer<typeof notificationPageSchema>

export const notificationRetryResponseSchema = z.object({
  delivery_id: z.uuid(),
  status: z.literal('queued'),
  retry_of_delivery_id: z.uuid(),
})
export const notificationDeliveryPageSchema = z.object({
  items: z.array(
    notificationDeliverySchema.extend({ organization_name: z.string(), created_at: timestamp }),
  ),
  pagination: notificationPageSchema.shape.pagination,
  delivery_enabled: z.boolean(),
})
export type NotificationRetryResponse = z.infer<typeof notificationRetryResponseSchema>
export type NotificationDeliveryPage = z.infer<typeof notificationDeliveryPageSchema>

export const geoScopeIdSchema = z.uuid()
export const geoAreaKindSchema = z.enum([
  'country',
  'region',
  'county',
  'municipality',
  'city',
  'district',
  'other',
])
export const geoAreaImportSchema = z
  .object({
    source: z.literal('osm'),
    source_type: z.literal('relation'),
    source_id: z.string().regex(/^[1-9][0-9]{0,18}$/),
  })
  .strict()
const geoAreaMetadata = {
  name: z.string().min(1).max(240),
  display_name: z.string().min(1).max(1024),
  country_code: z
    .string()
    .regex(/^[a-z]{2}$/)
    .nullable(),
  admin_level: z.number().int().min(0).max(99).nullable(),
  kind: geoAreaKindSchema,
  provider_class: z.string().max(80).nullable(),
  provider_type: z.string().max(80).nullable(),
  provider_addresstype: z.string().max(80).nullable(),
  bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]).nullable(),
  hierarchy: z.record(z.string().max(80), z.string().max(240)),
}
export const geoAreaSchema = z.object({
  id: geoScopeIdSchema,
  source: z.string().min(1).max(80),
  source_type: z.string().min(1).max(80),
  source_id: z.string().min(1).max(80),
  ...geoAreaMetadata,
  fetched_at: z.iso.datetime({ offset: true }),
})
export const geoAreaSearchItemSchema = z.object({
  provider: z.literal('osm'),
  osm_type: z.literal('relation'),
  osm_id: geoAreaImportSchema.shape.source_id,
  ...geoAreaMetadata,
  eligible_for_scope: z.boolean(),
})
export const geoAreaSearchResponseSchema = z.object({
  items: z.array(geoAreaSearchItemSchema).max(10),
})
export type GeoArea = z.infer<typeof geoAreaSchema>
export type GeoAreaKind = z.infer<typeof geoAreaKindSchema>
export type GeoAreaSearchItem = z.infer<typeof geoAreaSearchItemSchema>
export type GeoAreaImport = z.infer<typeof geoAreaImportSchema>

export const geocodeStatusSchema = z.enum([
  'pending',
  'checking',
  'candidate',
  'ambiguous',
  'not_found',
  'insufficient_input',
  'failed',
  'stale',
])
export const geocodeMatchReasonSchema = z.enum([
  'country_exact',
  'country_mismatch',
  'country_unknown',
  'postal_code_exact',
  'postal_code_mismatch',
  'postal_code_missing',
  'city_exact',
  'city_mismatch',
  'city_missing',
  'street_exact',
  'street_mismatch',
  'street_missing',
  'house_number_exact',
  'house_number_mismatch',
  'house_number_missing',
])
export const geocodeCandidateSchema = z.object({
  id: z.uuid(),
  rank: z.number().int().min(1).max(5),
  latitude: z.number().min(-90).max(90),
  longitude: z.number().min(-180).max(180),
  display_name: z.string().min(1).max(1024),
  osm_type: z.enum(['node', 'way', 'relation']).nullable(),
  osm_id: z
    .string()
    .regex(/^[1-9][0-9]{0,18}$/)
    .nullable(),
  provider_class: z.string().nullable(),
  provider_type: z.string().nullable(),
  provider_addresstype: z.string().nullable(),
  provider_importance: z.number().nullable(),
  match_score: z.number().min(0).max(1),
  match_reasons: z.array(geocodeMatchReasonSchema),
  address: z.partialRecord(
    z.enum([
      'road',
      'house_number',
      'postcode',
      'city',
      'town',
      'village',
      'municipality',
      'county',
      'state',
      'country',
      'country_code',
    ]),
    z.string().max(240),
  ),
  osm_url: z
    .string()
    .regex(
      /^https:\/\/www\.openstreetmap\.org\/(?:node\/[1-9][0-9]{0,18}|way\/[1-9][0-9]{0,18}|relation\/[1-9][0-9]{0,18}|\?mlat=-?[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?&mlon=-?[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?)$/,
    ),
})
export const geocodeRequestSummarySchema = z.object({
  id: z.uuid(),
  entity_type: z.enum(['organization', 'venue']),
  entity_key: z.uuid(),
  entity_name: z.string(),
  source_address: z.string(),
  status: geocodeStatusSchema,
  source_fingerprint: z.string(),
  query_fingerprint: z.string(),
  generation: z.number().int().positive(),
  query_version: z.number().int().positive(),
  scoring_version: z.number().int().positive(),
  attempt_count: z.number().int().nonnegative(),
  checked_at: timestamp.nullable(),
  next_check_at: timestamp.nullable(),
  last_error: z.literal('provider_unavailable').nullable(),
  created_at: timestamp,
  updated_at: timestamp,
  candidate_count: z.number().int().min(0).max(5),
  best_candidate: geocodeCandidateSchema.nullable(),
})
export const geocodeRequestDetailSchema = geocodeRequestSummarySchema.extend({
  candidates: z.array(geocodeCandidateSchema).max(5),
})
export const geocodePageSchema = z.object({
  items: z.array(geocodeRequestSummarySchema),
  pagination: notificationPageSchema.shape.pagination,
  counts: z.partialRecord(geocodeStatusSchema, z.number().int().nonnegative()),
})
export const geocodeRetryResponseSchema = z.object({ id: z.uuid(), status: z.literal('pending') })
export type GeocodeStatus = z.infer<typeof geocodeStatusSchema>
export type GeocodeCandidate = z.infer<typeof geocodeCandidateSchema>
export type GeocodeRequestDetail = z.infer<typeof geocodeRequestDetailSchema>
export type GeocodePage = z.infer<typeof geocodePageSchema>
export interface GeocodeFilters {
  entity_type?: 'organization' | 'venue'
  status?: GeocodeStatus
  page?: number
  page_size?: number
}

// Explicit diagnostic projection allowlist: never accept secret source columns.
const diagnosticColumnSchema = z.enum([
  'uuid',
  'event_uuid',
  'start_date',
  'start_time',
  'end_date',
  'end_time',
  'all_day',
  'release_status',
  'date_venue_uuid',
  'date_space_uuid',
  'event_venue_uuid',
  'event_space_uuid',
  'online_link',
  'title',
  'min_price',
  'max_price',
  'currency',
  'price_type',
  'name',
  'org_uuid',
  'street',
  'house_number',
  'postal_code',
  'city',
  'country',
  'state',
  'osm_id',
  'point',
  'point_missing',
  'source_link',
  'ticket_link',
  'registration_link',
  'web_link',
  'organization_name',
  'user_uuid',
  'has_joined',
  'accept_token_present',
  'from_org_uuid',
  'from_org_name',
  'to_org_uuid',
  'to_org_name',
  'user_id',
  'user_exists',
  'status',
  'created_at',
  'grant_exists',
])
const diagnosticValueSchema = z.union([
  z.string().max(4096),
  z.number().finite(),
  z.boolean(),
  z.null(),
])
export const diagnosticRequestSchema = z
  .object({
    finding_id: z.string().min(1).max(8192),
    mode: z.enum(['persisted', 'live']).optional(),
  })
  .strict()
export const sqlDiagnosticDefinitionSchema = z
  .object({
    recipe_id: z.string(),
    title: z.string(),
    datasource: z.literal('uranus'),
    readonly: z.literal(true),
    sql: z.string(),
    copy_sql: z.string(),
    console_sql: z.string().nullable().optional(),
    parameters: z.record(z.string(), diagnosticValueSchema),
    explanation: z.string(),
    columns: z.array(diagnosticColumnSchema),
    last_seen_at: z.iso.datetime().nullable(),
  })
  .strict()
export const sqlDiagnosticResultSchema = z
  .object({
    recipe_id: z.string(),
    columns: z.array(diagnosticColumnSchema),
    rows: z
      .array(
        z
          .record(z.string(), diagnosticValueSchema)
          .refine((row) =>
            Object.keys(row).every((key) => diagnosticColumnSchema.safeParse(key).success),
          ),
      )
      .max(100),
    row_count: z.number().int().min(0).max(100),
    duration_ms: z.number().nonnegative(),
    observed_at: z.iso.datetime(),
    evaluation: z
      .object({
        engine: z.literal('Python'),
        matched: z.boolean().nullable(),
        message: z.string(),
        checks: z.array(
          z
            .object({
              label: z.string(),
              value: z.boolean().nullable(),
              left: diagnosticValueSchema,
              operator: z.string().nullable(),
              right: diagnosticValueSchema,
            })
            .strict(),
        ),
      })
      .strict(),
  })
  .strict()
  .refine(
    (result) =>
      result.row_count === result.rows.length &&
      result.rows.every(
        (row) =>
          Object.keys(row).length === result.columns.length &&
          result.columns.every((column) => column in row),
      ),
  )
export type SqlDiagnosticDefinition = z.infer<typeof sqlDiagnosticDefinitionSchema>
export type SqlDiagnosticResult = z.infer<typeof sqlDiagnosticResultSchema>

export { provenanceDefinitionSchema, provenanceResultSchema } from './sql-provenance'
