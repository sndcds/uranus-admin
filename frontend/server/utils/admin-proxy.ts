import {
  researchQuerySchema,
  diagnosticRequestSchema,
  geoAreaImportSchema,
  loginSchema,
  sessionSchema,
  logoutSchema,
  adminErrorSchema,
  adminErrorStatuses,
  reviewUpdateSchema,
  markCreateSchema,
  markUpdateSchema,
  assignmentCreateSchema,
  assignmentLookupSchema,
  assignmentUpdateSchema,
} from '#shared/contracts'
import {
  provenanceViews,
  validProvenanceParams,
  type ProvenanceView,
} from '../../shared/sql-provenance'
import { isIP } from 'node:net'
import { failure } from '#shared/errors'

const routes: Record<string, readonly string[]> = {
  '/api/v1/admins': [],
  '/api/v1/assignments': ['finding_id', 'workflow_type', 'workflow_key'],
  '/api/v1/inbox': ['scope', 'attention', 'kind', 'entity_type', 'page', 'page_size'],
  '/api/v1/geocode/requests': ['entity_type', 'status', 'page', 'page_size'],
  '/api/v1/geo/areas/search': ['q', 'limit'],
  '/api/v1/geo/areas': [],
  '/api/v1/notification-deliveries': [
    'status',
    'organization_id',
    'delivery_kind',
    'days',
    'page',
    'page_size',
  ],
  '/api/v1/notifications': [
    'status',
    'notification_type',
    'organization_id',
    'days',
    'page',
    'page_size',
  ],
  '/api/v1/statistics/events/content': ['geo_scope_id', 'period', 'status', 'compare'],
  '/api/v1/statistics/entities': [
    'geo_scope_id',
    'period',
    'interval',
    'compare',
    'from_at',
    'to_at',
  ],
  '/api/v1/graph': ['root_type', 'root_key', 'depth', 'relation_type'],
  '/api/v1/search': ['q', 'limit_per_type', 'types'],
  '/api/v1/entity-search': [
    'q',
    'geo_scope_id',
    'entity_type',
    'organization_id',
    'status',
    'period',
    'temporal',
    'limit',
  ],
  '/api/v1/graph/search': ['geo_scope_id', 'q', 'entity_type', 'organization_id', 'limit'],
  '/auth/login': [],
  '/auth/logout': [],
  '/auth/session': [],
  '/api/v1/record-marks': [
    'entity_type',
    'entity_key',
    'status',
    'urgency',
    'reason',
    'sort',
    'page',
    'page_size',
  ],
  '/api/v1/check-runs': ['page', 'page_size'],
  '/api/v1/finding-reviews': [],
  '/api/v1/work-queues/partner_requests': [
    'organization_id',
    'entity_key',
    'status',
    'min_age_days',
    'page',
    'page_size',
  ],
  '/api/v1/work-queues/team_invitations': [
    'organization_id',
    'entity_key',
    'membership_status',
    'min_age_days',
    'page',
    'page_size',
  ],
  '/api/v1/work-queues/user_activation': [
    'organization_id',
    'entity_key',
    'status',
    'min_age_days',
    'page',
    'page_size',
  ],
  '/health': [],
  '/ready': [],
  '/api/v1/dashboard/summary': ['geo_scope_id', 'period', 'mode'],
  '/api/v1/dashboard/activity': [
    'geo_scope_id',
    'cursor',
    'creation_basis',
    'entity_type',
    'entity_key',
    'organization_id',
    'period',
    'from_at',
    'to_at',
    'timestamp_state',
    'page',
    'page_size',
  ],
  '/api/v1/findings/sql-diagnostic': ['finding_id', 'mode'],
  '/api/v1/findings/sql-diagnostic/execute': [],
  '/api/v1/findings': [
    'active_only',
    'geo_scope_id',
    'cursor',
    'mode',
    'severity',
    'entity_type',
    'entity_key',
    'rule',
    'organization_id',
    'status',
    'page',
    'page_size',
  ],
  '/api/v1/quality/venues/missing-geolocation': ['organization_id', 'page', 'page_size'],
}
export interface ProxyInput {
  path: string
  method: string
  query: URLSearchParams
  clientIp?: string
  authorization?: string
  sessionCookie?: string
  origin?: string
  csrf?: string
  body?: unknown
}
export interface ProxyResult {
  status: number
  body: unknown
  setCookies?: string[]
}
function rejected(status: number, code: string): ProxyResult {
  const detail = failure(status, code)
  return { status, body: { error: { code: detail.code, message: detail.message } } }
}

export async function forwardAdminRequest(
  input: ProxyInput,
  base: string,
  fetcher: typeof fetch = fetch,
): Promise<ProxyResult> {
  const geocodeDetail =
    /^\/api\/v1\/geocode\/requests\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      input.path,
    )
  const geocodeRetry =
    /^\/api\/v1\/geocode\/requests\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/retry$/i.test(
      input.path,
    )
  const geoDetail =
    /^\/api\/v1\/geo\/areas\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      input.path,
    )
  const spatialList = /^\/api\/v1\/(events|venues|spaces|organizations)$/.test(input.path)
  const entityList = /^\/api\/v1\/(events|venues|spaces|organizations|users|images)$/.test(
    input.path,
  )
  const entityDetail =
    /^\/api\/v1\/(events|venues|spaces|organizations|users|images)\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      input.path,
    )
  const entityTimeline =
    /^\/api\/v1\/entities\/(event|organization|venue|space|user|image)\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/timeline$/i.test(
      input.path,
    )
  const markDetail =
    /^\/api\/v1\/record-marks\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      input.path,
    )
  const assignmentDetail =
    /^\/api\/v1\/assignments\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      input.path,
    )
  const checkDetail =
    /^\/api\/v1\/check-runs\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      input.path,
    )
  const notificationDetail =
    /^\/api\/v1\/(notifications|notification-deliveries)\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      input.path,
    )
  const notificationRetry =
    /^\/api\/v1\/notification-deliveries\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/retry$/i.test(
      input.path,
    )
  const notificationPreview =
    /^\/api\/v1\/notifications\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/preview$/i.test(
      input.path,
    )
  const provenanceMatch = input.path.match(
    /^\/api\/v1\/sql-provenance\/([a-z_.-]+)(?:\/([a-z_0-9.-]{1,150})\/execute)?$/,
  )
  const provenanceView = provenanceMatch?.[1]
  const provenanceExecute = !!provenanceMatch?.[2]
  if (
    provenanceMatch &&
    (!provenanceView ||
      !Object.hasOwn(provenanceViews, provenanceView) ||
      (provenanceExecute && !provenanceMatch[2]!.startsWith(provenanceView + '.')))
  )
    return rejected(404, 'route_not_allowed')
  const researchList = /^\/api\/v1\/research\/(search|export|events|venues|organizations)$/.test(
    input.path,
  )
  const researchDetail =
    /^\/api\/v1\/research\/(events|venues|organizations)\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      input.path,
    )
  const researchOptions = input.path === '/api/v1/research/options'
  if (
    (researchList || researchDetail) &&
    !researchQuerySchema.safeParse(Object.fromEntries(input.query)).success
  )
    return rejected(422, 'invalid_query')
  const allowed =
    researchList || researchDetail
      ? [
          'q',
          'entity_type',
          'from_date',
          'to_date',
          'city',
          'category',
          'status',
          'organization_id',
          'venue_id',
          'sort',
          'page',
          'page_size',
        ]
      : researchOptions
        ? []
        : provenanceView
          ? provenanceExecute
            ? []
            : (provenanceViews[provenanceView as ProvenanceView] as readonly string[])
          : notificationDetail || notificationRetry || geoDetail || geocodeDetail || geocodeRetry
            ? []
            : entityTimeline
              ? ['cursor', 'page_size']
              : notificationPreview
                ? ['locale']
                : entityList
                  ? [
                      'q',
                      'organization_id',
                      'status',
                      'period',
                      'temporal',
                      'page',
                      'page_size',
                      ...(input.path === '/api/v1/venues' ? ['scope'] : []),
                      ...(spatialList ? ['geo_scope_id'] : []),
                    ]
                  : entityDetail
                    ? ['related_page']
                    : markDetail || assignmentDetail || checkDetail
                      ? []
                      : Object.hasOwn(routes, input.path)
                        ? routes[input.path]
                        : undefined
  if (!allowed) return rejected(404, 'route_not_allowed')
  const diagnosticExecute = input.path === '/api/v1/findings/sql-diagnostic/execute'
  const authWrite = input.method === 'POST' && ['/auth/login', '/auth/logout'].includes(input.path)
  if (
    input.path.startsWith('/auth/') &&
    !authWrite &&
    !(input.path === '/auth/session' && input.method === 'GET')
  )
    return rejected(405, 'method_not_allowed')
  const write =
    authWrite ||
    (input.method === 'POST' && provenanceExecute) ||
    (input.method === 'POST' && diagnosticExecute) ||
    (input.method === 'POST' && input.path === '/api/v1/geo/areas') ||
    (input.method === 'POST' && (notificationRetry || geocodeRetry)) ||
    (input.method === 'POST' && input.path === '/api/v1/record-marks') ||
    (input.method === 'PATCH' && markDetail) ||
    (input.method === 'POST' && input.path === '/api/v1/assignments') ||
    (input.method === 'PATCH' && assignmentDetail) ||
    (input.method === 'POST' && input.path === '/api/v1/check-runs') ||
    (input.method === 'PATCH' && input.path === '/api/v1/finding-reviews')
  if (
    !write &&
    (input.method !== 'GET' ||
      input.path === '/api/v1/finding-reviews' ||
      diagnosticExecute ||
      provenanceExecute ||
      notificationRetry ||
      geocodeRetry)
  )
    return rejected(405, 'method_not_allowed')
  if ((notificationRetry || geocodeRetry) && input.body !== undefined)
    return rejected(422, 'invalid_input')
  if (write && input.query.size) return rejected(422, 'invalid_query')
  if (input.path === '/api/v1/geo/areas' && input.method !== 'POST')
    return rejected(405, 'method_not_allowed')
  let requestBody: string | undefined
  if (provenanceExecute && provenanceView) {
    const params = validProvenanceParams(provenanceView, input.body)
    if (!params) return rejected(422, 'invalid_input')
    requestBody = JSON.stringify(params)
  }
  if (diagnosticExecute) {
    const parsed = diagnosticRequestSchema.safeParse(input.body)
    if (!parsed.success) return rejected(422, 'invalid_input')
    requestBody = JSON.stringify(parsed.data)
  }
  if (write && input.path === '/api/v1/geo/areas') {
    const parsed = geoAreaImportSchema.safeParse(input.body)
    if (!parsed.success) return rejected(422, 'invalid_input')
    requestBody = JSON.stringify(parsed.data)
  }
  if (input.path === '/auth/login') {
    const parsed = loginSchema.safeParse(input.body)
    if (!parsed.success) return rejected(422, 'invalid_input')
    requestBody = JSON.stringify(parsed.data)
  }
  if (
    input.path === '/auth/logout' &&
    input.body !== undefined &&
    (input.body === null ||
      typeof input.body !== 'object' ||
      Array.isArray(input.body) ||
      Object.keys(input.body).length)
  )
    return rejected(422, 'invalid_input')
  const cookie = input.sessionCookie
  if (cookie && !/^(?:__Host-admin_session|admin_session)=[A-Za-z0-9_-]{43}$/.test(cookie))
    return rejected(401, 'invalid_credentials')
  if (write && (markDetail || input.path === '/api/v1/record-marks')) {
    const parsed = (markDetail ? markUpdateSchema : markCreateSchema).safeParse(input.body)
    if (!parsed.success) return rejected(422, 'invalid_input')
    requestBody = JSON.stringify(parsed.data)
  }
  if (write && (assignmentDetail || input.path === '/api/v1/assignments')) {
    const parsed = (assignmentDetail ? assignmentUpdateSchema : assignmentCreateSchema).safeParse(
      input.body,
    )
    if (!parsed.success) return rejected(422, 'invalid_input')
    requestBody = JSON.stringify(parsed.data)
  }
  if (write && input.path === '/api/v1/finding-reviews') {
    const parsed = reviewUpdateSchema.safeParse(input.body)
    if (!parsed.success) return rejected(422, 'invalid_input')
    requestBody = JSON.stringify(parsed.data)
  }
  if (
    write &&
    input.path === '/api/v1/check-runs' &&
    input.body !== undefined &&
    (input.body === null ||
      typeof input.body !== 'object' ||
      Array.isArray(input.body) ||
      Object.keys(input.body).length)
  )
    return rejected(422, 'invalid_input')
  for (const key of input.query.keys()) {
    if (!allowed.includes(key) || input.query.getAll(key).length !== 1) {
      return rejected(422, 'invalid_query')
    }
  }
  if (
    provenanceView &&
    !provenanceExecute &&
    !validProvenanceParams(provenanceView, Object.fromEntries(input.query))
  )
    return rejected(422, 'invalid_query')
  if (
    input.path === '/api/v1/findings/sql-diagnostic' &&
    !diagnosticRequestSchema.safeParse(Object.fromEntries(input.query)).success
  )
    return rejected(422, 'invalid_query')
  if (
    input.path === '/api/v1/assignments' &&
    input.method === 'GET' &&
    !assignmentLookupSchema.safeParse(Object.fromEntries(input.query)).success
  )
    return rejected(422, 'invalid_query')
  if (
    input.path.startsWith('/api/') &&
    !cookie &&
    !/^Bearer [^\s\r\n]{1,8192}$/i.test(input.authorization ?? '')
  ) {
    return rejected(401, 'authentication_required')
  }
  let url: URL
  try {
    const origin = new URL(base)
    if (
      !['http:', 'https:'].includes(origin.protocol) ||
      origin.username ||
      origin.password ||
      origin.search ||
      origin.hash ||
      origin.pathname !== '/'
    )
      return rejected(503, 'invalid_upstream_configuration')
    url = new URL(input.path, origin)
    url.search = input.query.toString()
  } catch {
    return rejected(503, 'invalid_upstream_configuration')
  }
  const liveFindings =
    input.method === 'GET' &&
    input.path === '/api/v1/findings' &&
    input.query.get('mode') === 'live'
  // Leave two seconds for transport/error rendering within the client's 60s budget.
  // All other routes retain the existing 10s upstream bound.
  const timeoutSignal = AbortSignal.timeout(liveFindings ? 58_000 : 10_000)
  try {
    const headers: Record<string, string> = { Accept: 'application/json' }
    if (requestBody) headers['Content-Type'] = 'application/json'
    if (input.clientIp && isIP(input.clientIp)) headers['X-Forwarded-For'] = input.clientIp
    if (input.authorization) headers.Authorization = input.authorization
    if (cookie && (input.path.startsWith('/api/') || input.path.startsWith('/auth/')))
      headers.Cookie = cookie
    if (input.origin) headers.Origin = input.origin
    if (input.csrf === '1') headers['X-Admin-CSRF'] = '1'
    const response = await fetcher(url, {
      method: input.method,
      body: requestBody,
      headers,
      redirect: 'error',
      cache: 'no-store',
      credentials: 'omit',
      signal: timeoutSignal,
    })
    if (!response.ok) {
      if (response.headers.get('content-type')?.split(';')[0]?.trim() === 'application/json') {
        try {
          const raw: unknown = await response.json()
          const parsed = adminErrorSchema.safeParse(raw)
          if (parsed.success && adminErrorStatuses[parsed.data.error.code] === response.status)
            return rejected(response.status, parsed.data.error.code)
        } catch {
          /* Invalid JSON is sanitized with its original HTTP status. */
        }
      }
      return rejected(response.status, 'upstream_error')
    }
    let body: unknown
    try {
      body = await response.json()
    } catch (error) {
      if (error instanceof SyntaxError) return rejected(502, 'invalid_response')
      throw error
    }
    if (input.path.startsWith('/auth/')) {
      const parsed = (input.path === '/auth/logout' ? logoutSchema : sessionSchema).safeParse(body)
      if (!parsed.success) return rejected(503, 'auth_storage_unavailable')
      const setCookies = response.headers
        .getSetCookie()
        .filter((value) =>
          /^(?:__Host-admin_session|admin_session)=(?:[A-Za-z0-9_-]{43}|""|);/.test(value),
        )
      return { status: response.status, body: parsed.data, setCookies }
    }
    return { status: response.status, body }
  } catch (error) {
    if (timeoutSignal.aborted || (error instanceof Error && error.name === 'TimeoutError'))
      return rejected(504, liveFindings ? 'live_findings_timeout' : 'request_timeout')
    return rejected(502, 'network_error')
  }
}
