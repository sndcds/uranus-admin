import {
  queuePageSchema,
  checkRunPageSchema,
  checkRunSchema,
  findingSchema,
  findingPageSchema,
  summarySchema,
  healthSchema,
  errorSchema,
  activityPageSchema,
} from '#shared/contracts'
import type { z } from 'zod'
import type { FindingFilters, Period, ReviewUpdate } from '#shared/contracts'
import { AdminApiError, failure } from '#shared/errors'

export function createAdminApi(fetcher: typeof fetch = fetch) {
  // Per Nuxt app instance. Never a module-level credential or serializable store field.
  let credential = ''
  async function request<T>(
    path: string,
    schema: z.ZodType<T>,
    query: Record<string, string | number | undefined> = {},
    method = 'GET',
    requestBody?: unknown,
  ) {
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
        },
        cache: 'no-store',
        credentials: 'omit',
        signal: AbortSignal.timeout(method === 'GET' ? 12000 : 125000),
      })
    } catch {
      throw new AdminApiError(failure(502))
    }
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
    setCredential(value: string) {
      credential = value.trim()
    },
    clearCredential() {
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
    runCheck: () => request('/api/v1/check-runs', checkRunSchema, {}, 'POST', {}),
    review: (body: ReviewUpdate) =>
      request('/api/v1/finding-reviews', findingSchema, {}, 'PATCH', body),
    health: () => request('/health', healthSchema),
    ready: () => request('/ready', healthSchema),
  }
}
export type AdminApi = ReturnType<typeof createAdminApi>
