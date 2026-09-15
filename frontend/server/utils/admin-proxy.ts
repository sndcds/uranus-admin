import {
  adminErrorSchema,
  adminErrorStatuses,
  reviewUpdateSchema,
  markCreateSchema,
  markUpdateSchema,
} from '#shared/contracts'
import { failure } from '#shared/errors'

const routes: Record<string, readonly string[]> = {
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
  '/api/v1/dashboard/summary': ['period'],
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
  authorization?: string
  body?: unknown
}
export interface ProxyResult {
  status: number
  body: unknown
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
  const allowed = markDetail
    ? []
    : Object.hasOwn(routes, input.path)
      ? routes[input.path]
      : undefined
  if (!allowed) return rejected(404, 'route_not_allowed')
  const write =
    (input.method === 'POST' && input.path === '/api/v1/record-marks') ||
    (input.method === 'PATCH' && markDetail) ||
    (input.method === 'POST' && input.path === '/api/v1/check-runs') ||
    (input.method === 'PATCH' && input.path === '/api/v1/finding-reviews')
  if (!write && (input.method !== 'GET' || input.path === '/api/v1/finding-reviews'))
    return rejected(405, 'method_not_allowed')
  if (write && input.query.size) return rejected(422, 'invalid_query')
  let requestBody: string | undefined
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
    if (input.authorization) headers.Authorization = input.authorization
    const response = await fetcher(url, {
      method: input.method,
      body: requestBody,
      headers,
      redirect: 'error',
      cache: 'no-store',
      signal: AbortSignal.timeout(write ? 120000 : 10000),
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
    return { status: response.status, body }
  } catch (error) {
    return rejected(
      error instanceof Error && error.name === 'TimeoutError' ? 504 : 502,
      'upstream_unavailable',
    )
  }
}
