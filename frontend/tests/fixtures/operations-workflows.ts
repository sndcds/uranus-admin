import type { FindingPage, InboxPage, MarkDetail } from '../../shared/contracts'
import { operationsFindings } from './operations-dashboard'
import { inboxFixture, unassignedFindingInboxFixture } from './inbox'
import { layoutMark } from './layout'

export const workflowFindings: FindingPage = {
  ...operationsFindings,
  pagination: { page: 1, page_size: 50, total: 929, pages: 19 },
  items: operationsFindings.items.map((finding, index) => ({
    ...finding,
    first_seen_at: '2026-09-21T08:00:00Z',
    image_url:
      index === 0 || index === 2
        ? `https://api.kulturbytes.de/api/image/00000000-0000-4000-8000-00000000006${index}?width=320&type=png`
        : null,
    status: index === 1 ? 'in_progress' : index === 3 ? 'exception' : 'open',
    exception_reason: index === 3 ? 'Adresse wird durch den Veranstalter geprüft.' : null,
    location_suggestion_request_id:
      index === 2 ? inboxFixture.items[0]!.assignment!.workflow_key : null,
    action:
      index >= 2
        ? {
            type: 'view',
            route: 'activity',
            entity_type: 'venue',
            entity_key: finding.entity_key,
            href: `/venues/${finding.entity_key}`,
          }
        : null,
  })),
}
export const workflowInbox: InboxPage = {
  ...inboxFixture,
  items: [
    { ...unassignedFindingInboxFixture.items[0]!, entity_name: 'Küstenkonzert · Abendtermin' },
    { ...inboxFixture.items[0]!, is_overdue: true, due_at: '2026-09-22T21:59:59Z' },
    {
      ...inboxFixture.items[0]!,
      id: 'geocode:synthetic',
      kind: 'geocode_request',
      assignment: null,
      entity_name: 'Atelier am Markt',
      due_at: null,
    },
    {
      ...inboxFixture.items[0]!,
      id: 'delivery:synthetic',
      kind: 'notification_delivery',
      assignment: null,
      title: 'Benachrichtigung',
      summary: 'Zustellung dauerhaft fehlgeschlagen',
      workflow_status: 'permanent_failure',
      candidate_count: null,
      entity_name: 'Bühne West',
      due_at: null,
      href: '/notifications/deliveries/00000000-0000-4000-8000-000000000900',
    },
    {
      ...inboxFixture.items[0]!,
      id: 'assignment:today',
      entity_name: 'Kulturhaus Nord',
      due_today: true,
    },
  ],
  counts: { critical: 1, mine: 2, unassigned: 3, due_today: 1, overdue: 1, snoozed: 0 },
  pagination: { page: 1, page_size: 25, total: 5, pages: 1 },
}
export const workflowMarks: MarkDetail[] = [
  'Kulturnacht am Hafen',
  'Atelier am Markt',
  'Bühne West',
  'Sommerkonzert',
].map((name, index) => ({
  ...layoutMark,
  id: `20000000-0000-4000-8000-00000000008${index}`,
  entity_name: name,
  status: index === 2 ? 'done' : index === 1 ? 'in_progress' : 'open',
  urgency: index === 0 ? 'urgent' : index === 1 ? 'high' : 'normal',
  reasons: index === 0 ? ['incorrect', 'incomplete'] : ['low_quality'],
  completed_at: index === 2 ? '2026-09-23T09:00:00Z' : null,
  completed_by: index === 2 ? layoutMark.created_by : null,
}))
