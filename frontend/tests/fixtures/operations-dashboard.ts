import type { DashboardSummary, FindingPage } from '../../shared/contracts'
import { summary, findings } from './api'

// Entirely synthetic; no production records or system health claims.
const run = {
  id: '10000000-0000-4000-8000-000000000099',
  status: 'success' as const,
  started_at: '2026-09-23T08:00:00Z',
  finished_at: '2026-09-23T08:03:00Z',
  rule_count: 47,
  finding_count: 929,
}
export const operationsSummary: DashboardSummary = {
  ...summary,
  from_at: '2026-09-22T10:00:00Z',
  to_at: '2026-09-23T10:00:00Z',
  new_records: {
    total: 56,
    organizations: 12,
    venues: 3,
    spaces: 0,
    events: 8,
    event_dates: 16,
    users: 5,
    partner_requests: 2,
    team_memberships: 3,
    images: 7,
  },
  urgent_findings: 156,
  quality: {
    total: 929,
    errors: 194,
    warnings: 602,
    info: 133,
    mode: 'persisted',
    rules: [
      'venue_missing_location',
      'venue_missing_logo',
      'organization_missing_logo',
      'event_date_end_before_start',
      'logo_unsupported_format',
      'postal_code_whitespace',
    ],
    rule_counts: {
      venue_missing_location: 254,
      venue_missing_logo: 201,
      organization_missing_logo: 103,
      event_date_end_before_start: 194,
      logo_unsupported_format: 133,
      postal_code_whitespace: 44,
    },
  },
  check_status: { latest_run: run, last_successful_run: run },
}
export const operationsFindings: FindingPage = {
  ...findings,
  mode: 'persisted',
  observed_at: '2026-09-23T10:00:00Z',
  pagination: { page: 1, page_size: 4, total: 929, pages: 233 },
  items: [
    {
      name: 'Küstenkonzert',
      organization: 'Kulturverein Nord',
      severity: 'error' as const,
      priority: 1,
    },
    {
      name: 'Lange Nacht der Kultur',
      organization: 'Bühne West',
      severity: 'error' as const,
      priority: 2,
    },
    {
      name: 'Hafenbühne',
      organization: 'Kulturverein Nord',
      severity: 'warning' as const,
      priority: 3,
    },
    {
      name: 'Atelier am Markt',
      organization: 'Kunsthaus Mitte',
      severity: 'warning' as const,
      priority: 4,
    },
  ].map((row, index) => ({
    ...findings.items[0]!,
    id: `synthetic-finding-${index}`,
    entity_key: `00000000-0000-4000-8000-00000000002${index}`,
    entity_name: row.name,
    organization_name: row.organization,
    severity: row.severity,
    priority: row.priority,
    rule: index < 2 ? 'event_date_end_before_start' : 'venue_missing_location',
    field: index < 2 ? 'end_date' : 'point',
    entity_type: index < 2 ? 'event_date' : 'venue',
    message:
      index < 2
        ? 'Enddatum liegt vor dem Startdatum.'
        : 'Geoposition fehlt; kommende Termine sind betroffen.',
    sql_diagnostic_available: index === 2,
    last_seen_at: '2026-09-23T08:03:00Z',
  })),
}
