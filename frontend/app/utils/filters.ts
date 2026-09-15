import { filtersSchema } from '#shared/contracts'
import type { FindingFilters } from '#shared/contracts'

export function parseFilters(query: Record<string, unknown>) {
  const allowed = new Set([
    'mode',
    'severity',
    'entity_type',
    'rule',
    'organization_id',
    'status',
    'page',
    'page_size',
  ])
  if (Object.keys(query).some((key) => !allowed.has(key))) return null
  const parsed = filtersSchema.safeParse(query)
  return parsed.success ? parsed.data : null
}
export function filterQuery(filters: FindingFilters): Record<string, string> {
  const result: Record<string, string> = {}
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') result[key] = String(value)
  }
  return result
}
