import {
  sessionSchema,
  logoutSchema,
  queuePageSchema,
  checkRunPageSchema,
  checkRunSchema,
  findingSchema,
  findingPageSchema,
  summarySchema,
  healthSchema,
  errorSchema,
  activityPageSchema,
  markPageSchema,
  markDetailSchema,
} from '#shared/contracts'
import type { z } from '#shared/zod'
import type {
  FindingFilters,
  Period,
  ReviewUpdate,
  MarkCreate,
  MarkUpdate,
} from '#shared/contracts'
import { AdminApiError, failure } from '#shared/errors'

export function createAdminApi(fetcher: typeof fetch = fetch) {
  // Per Nuxt app instance. Never a module-level credential or serializable store field.
  let credential = ''
  let accessLost: ((status: number) => void) | undefined
  let accessGeneration = 0
  async function request<T>(
    path: string,
    schema: z.ZodType<T>,
    query: Record<string, string | number | undefined> = {},
    method = 'GET',
    requestBody?: unknown,
  ) {
    const generation = accessGeneration
    const params = new URLSearchParams()
    for (const [key, value] of Object.entries(query))
      if (value !== undefined) params.set(key, String(value))
    let response: Response
    try {
      response = await fetcher(`/api/admin${path}${params.size ? `?${params}` : ''}`, {
        method,
        body: requestBody === undefined ? undefined : JSON.stringify(requestBody),
        headers: {
          ...(credential ? { Authorization: `Bearer ${credential}` } : {}),
          ...(requestBody === undefined ? {} : { 'Content-Type': 'application/json' }),
          ...(method === 'GET' ? {} : { 'X-Admin-CSRF': '1' }),
        },
        cache: 'no-store',
        credentials: credential ? 'omit' : 'same-origin',
        signal: AbortSignal.timeout(12000),
      })
    } catch {
      throw new AdminApiError(failure(502))
    }
    if (
      generation === accessGeneration &&
      [401, 403].includes(response.status) &&
      path.startsWith('/api/')
    )
      accessLost?.(response.status)
    let body: unknown
    try {
      body = await response.json()
    } catch {
      throw new AdminApiError(failure(response.ok ? 502 : response.status))
    }
    if (!response.ok) {
      const detail = errorSchema.safeParse(body)
      throw new AdminApiError(
        failure(response.status, detail.success ? detail.data.error.code : undefined),
      )
    }
    const parsed = schema.safeParse(body)
    if (!parsed.success) throw new AdminApiError(failure(502, 'invalid_response'))
    return parsed.data
  }
  return {
    onAccessLost(callback: (status: number) => void) {
      accessLost = callback
    },
    session: () => request('/auth/session', sessionSchema),
    login: async (login: string, password: string) => {
      const identity = await request('/auth/login', sessionSchema, {}, 'POST', { login, password })
      accessGeneration++
      return identity
    },
    logout: () => request('/auth/logout', logoutSchema, {}, 'POST'),
    setCredential(value: string) {
      accessGeneration++
      credential = value.trim()
    },
    clearCredential() {
      accessGeneration++
      credential = ''
    },
    summary: (period: Period) => request('/api/v1/dashboard/summary', summarySchema, { period }),
    findings: (filters: FindingFilters) => request('/api/v1/findings', findingPageSchema, filters),
    missingGeolocation: (page = 1) =>
      request('/api/v1/quality/venues/missing-geolocation', findingPageSchema, { page }),
    activity: (query: Record<string, string | number | undefined>) =>
      request('/api/v1/dashboard/activity', activityPageSchema, query),
    queue: (kind: string, query: Record<string, string | number | undefined>) =>
      request(`/api/v1/work-queues/${kind}`, queuePageSchema, query),
    checkRuns: (page = 1) => request('/api/v1/check-runs', checkRunPageSchema, { page }),
    checkRun: (id: string) =>
      request(`/api/v1/check-runs/${encodeURIComponent(id)}`, checkRunSchema),
    runCheck: () => request('/api/v1/check-runs', checkRunSchema, {}, 'POST', {}),
    review: (body: ReviewUpdate) =>
      request('/api/v1/finding-reviews', findingSchema, {}, 'PATCH', body),
    health: () => request('/health', healthSchema),
    marks: (query: Record<string, string | number | undefined>) =>
      request('/api/v1/record-marks', markPageSchema, query),
    mark: (id: string) =>
      request(`/api/v1/record-marks/${encodeURIComponent(id)}`, markDetailSchema),
    createMark: (body: MarkCreate) =>
      request('/api/v1/record-marks', markDetailSchema, {}, 'POST', body),
    updateMark: (id: string, body: MarkUpdate) =>
      request(
        `/api/v1/record-marks/${encodeURIComponent(id)}`,
        markDetailSchema,
        {},
        'PATCH',
        body,
      ),
    ready: () => request('/ready', healthSchema),
  }
}
export type AdminApi = ReturnType<typeof createAdminApi>
