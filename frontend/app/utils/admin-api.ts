import type { z } from 'zod'
import { findingPageSchema, summarySchema, healthSchema, errorSchema } from '#shared/contracts'
import type { FindingFilters, Period } from '#shared/contracts'
import { AdminApiError, failure } from '#shared/errors'

export function createAdminApi(fetcher: typeof fetch = fetch) {
  // Per Nuxt app instance. Never a module-level credential or serializable store field.
  let credential = ''
  async function request<T>(
    path: string,
    schema: z.ZodType<T>,
    query: Record<string, string | number | undefined> = {},
  ) {
    const params = new URLSearchParams()
    for (const [key, value] of Object.entries(query))
      if (value !== undefined) params.set(key, String(value))
    let response: Response
    try {
      response = await fetcher(`/api/admin${path}${params.size ? `?${params}` : ''}`, {
        headers: credential ? { Authorization: `Bearer ${credential}` } : {},
        cache: 'no-store',
        credentials: 'omit',
        signal: AbortSignal.timeout(12000),
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
    health: () => request('/health', healthSchema),
    ready: () => request('/ready', healthSchema),
  }
}
export type AdminApi = ReturnType<typeof createAdminApi>
