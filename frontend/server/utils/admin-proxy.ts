import {
  loginSchema,
  sessionSchema,
  logoutSchema,
  adminErrorSchema,
  adminErrorStatuses,
  reviewUpdateSchema,
  markCreateSchema,
  markUpdateSchema,
} from '#shared/contracts'
import { isIP } from 'node:net'
import { failure } from '#shared/errors'

const routes: Record<string, readonly string[]> = {
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
    'status',
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
  '/api/v1/dashboard/summary': ['period', 'mode'],
  '/api/v1/dashboard/activity': [
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
  '/api/v1/findings': [
    'mode',
    'severity',
    'entity_type',
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
  const markDetail =
    /^\/api\/v1\/record-marks\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      input.path,
    )
  const checkDetail =
    /^\/api\/v1\/check-runs\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
      input.path,
    )
  const allowed =
    markDetail || checkDetail
      ? []
      : Object.hasOwn(routes, input.path)
        ? routes[input.path]
        : undefined
  if (!allowed) return rejected(404, 'route_not_allowed')
  const authWrite = input.method === 'POST' && ['/auth/login', '/auth/logout'].includes(input.path)
  if (
    input.path.startsWith('/auth/') &&
    !authWrite &&
    !(input.path === '/auth/session' && input.method === 'GET')
  )
    return rejected(405, 'method_not_allowed')
  const write =
    authWrite ||
    (input.method === 'POST' && input.path === '/api/v1/record-marks') ||
    (input.method === 'PATCH' && markDetail) ||
    (input.method === 'POST' && input.path === '/api/v1/check-runs') ||
    (input.method === 'PATCH' && input.path === '/api/v1/finding-reviews')
  if (!write && (input.method !== 'GET' || input.path === '/api/v1/finding-reviews'))
    return rejected(405, 'method_not_allowed')
  if (write && input.query.size) return rejected(422, 'invalid_query')
  let requestBody: string | undefined
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
      signal: AbortSignal.timeout(10000),
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
    const body: unknown = await response.json()
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
    return rejected(
      error instanceof Error && error.name === 'TimeoutError' ? 504 : 502,
      'upstream_unavailable',
    )
  }
}
