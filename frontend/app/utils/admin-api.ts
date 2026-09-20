import {
  sqlDiagnosticDefinitionSchema,
  sqlDiagnosticResultSchema,
  geocodePageSchema,
  geocodeRequestDetailSchema,
  geocodeRetryResponseSchema,
  geoAreaSchema,
  geoAreaSearchResponseSchema,
  notificationPageSchema,
  notificationDeliveryPageSchema,
  notificationRetryResponseSchema,
  notificationDetailSchema,
  notificationDeliveryDetailSchema,
  notificationPreviewSchema,
  entityPageSchema,
  entitySearchResponseSchema,
  entityDetailSchema,
  entityStatisticsResponseSchema,
  eventContentStatisticsSchema,
  graphResponseSchema,
  graphSearchResponseSchema,
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
  GeocodeFilters,
  GeoAreaImport,
  FindingFilters,
  EventContentQuery,
  EntitySearchQuery,
  Period,
  ReviewUpdate,
  MarkCreate,
  MarkUpdate,
} from '#shared/contracts'
import { AdminApiError, failure } from '#shared/errors'

export function createAdminApi(
  fetcher: (path: string, options: RequestInit) => Promise<Response> = fetch,
) {
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
    signal?: AbortSignal,
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
        signal: signal
          ? AbortSignal.any([signal, AbortSignal.timeout(12000)])
          : AbortSignal.timeout(12000),
      })
    } catch {
      throw new AdminApiError(failure(502))
    }
    if (generation === accessGeneration && response.status === 401 && path.startsWith('/api/'))
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
    geocodeRequests: (query: GeocodeFilters) =>
      request('/api/v1/geocode/requests', geocodePageSchema, { ...query }),
    geocodeRequest: (id: string) =>
      request(`/api/v1/geocode/requests/${encodeURIComponent(id)}`, geocodeRequestDetailSchema),
    retryGeocodeRequest: (id: string) =>
      request(
        `/api/v1/geocode/requests/${encodeURIComponent(id)}/retry`,
        geocodeRetryResponseSchema,
        {},
        'POST',
      ),
    geoArea: (id: string) => request(`/api/v1/geo/areas/${encodeURIComponent(id)}`, geoAreaSchema),
    searchGeoAreas: (q: string, signal?: AbortSignal) =>
      request(
        '/api/v1/geo/areas/search',
        geoAreaSearchResponseSchema,
        { q },
        'GET',
        undefined,
        signal,
      ),
    importGeoArea: (identity: GeoAreaImport) =>
      request('/api/v1/geo/areas', geoAreaSchema, {}, 'POST', identity),
    onAccessLost(callback: (status: number) => void) {
      accessLost = callback
    },
    notifications: (query: Record<string, string | number | undefined>) =>
      request('/api/v1/notifications', notificationPageSchema, query),
    notification: (id: string) =>
      request(`/api/v1/notifications/${encodeURIComponent(id)}`, notificationDetailSchema),
    notificationDeliveries: (query: Record<string, string | number | undefined>) =>
      request('/api/v1/notification-deliveries', notificationDeliveryPageSchema, query),
    retryNotificationDelivery: (id: string) =>
      request(
        `/api/v1/notification-deliveries/${encodeURIComponent(id)}/retry`,
        notificationRetryResponseSchema,
        {},
        'POST',
      ),
    notificationDelivery: (id: string) =>
      request(
        `/api/v1/notification-deliveries/${encodeURIComponent(id)}`,
        notificationDeliveryDetailSchema,
      ),
    notificationPreview: (id: string, locale: 'de' | 'da' | 'en') =>
      request(
        `/api/v1/notifications/${encodeURIComponent(id)}/preview`,
        notificationPreviewSchema,
        { locale },
      ),
    entitySearch: (query: EntitySearchQuery) =>
      request('/api/v1/entity-search', entitySearchResponseSchema, query),
    entities: (section: string, query: Record<string, string | number | undefined>) =>
      request(`/api/v1/${section}`, entityPageSchema, query),
    entity: (section: string, id: string, relatedPage = 1) =>
      request(`/api/v1/${section}/${encodeURIComponent(id)}`, entityDetailSchema, {
        related_page: relatedPage,
      }),
    eventContent: (query: EventContentQuery) =>
      request('/api/v1/statistics/events/content', eventContentStatisticsSchema, query),
    statistics: (query: Record<string, string | number | undefined>) =>
      request('/api/v1/statistics/entities', entityStatisticsResponseSchema, query),
    graph: (query: Record<string, string | number | undefined>) =>
      request('/api/v1/graph', graphResponseSchema, query),
    graphSearch: (query: Record<string, string | number | undefined>) =>
      request('/api/v1/graph/search', graphSearchResponseSchema, query),
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
    summary: (period: Period, geo_scope_id?: string) =>
      request('/api/v1/dashboard/summary', summarySchema, { period, geo_scope_id }),
    sqlDiagnostic: (finding_id: string) =>
      request('/api/v1/findings/sql-diagnostic', sqlDiagnosticDefinitionSchema, { finding_id }),
    executeSqlDiagnostic: (finding_id: string) =>
      request('/api/v1/findings/sql-diagnostic/execute', sqlDiagnosticResultSchema, {}, 'POST', {
        finding_id,
      }),
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
