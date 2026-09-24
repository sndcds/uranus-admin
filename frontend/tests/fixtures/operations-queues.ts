import type { Page } from '@playwright/test'
import type {
  QueuePage,
  NotificationDeliveryDetail,
  NotificationPage,
} from '../../shared/contracts'
import { membershipFixture } from './memberships'
import {
  notification,
  notificationPage,
  notificationDelivery,
  notificationPreview,
} from './notifications'
import { mockLayoutApi } from './layout'

export const stamp = '2026-09-24T08:00:00Z'
export function queueOperations(kind: QueuePage['kind']): QueuePage {
  const base = membershipFixture(false).items[0]!
  return {
    kind,
    observed_at: stamp,
    pagination: { page: 1, page_size: 25, total: 3, pages: 1 },
    items: ['Kulturhaus am Hafen', 'Atelier Nord', 'Musikverein West'].map((name, i) => {
      const key = `10000000-0000-4000-8000-00000000010${i}`
      const user = `10000000-0000-4000-8000-00000000011${i}`
      const entity_key =
        kind === 'team_invitations'
          ? `membership:${key}:${user}`
          : kind === 'partner_requests'
            ? `partner-request:${key}:${user}`
            : user
      return {
        ...base,
        entity_key,
        organization_id: key,
        organization_name: name,
        user_id: user,
        user_name: ['Anna Beispiel', 'Lars Muster', 'Mira Test'][i]!,
        from_organization_id: kind === 'partner_requests' ? key : null,
        from_organization_name: kind === 'partner_requests' ? name : null,
        to_organization_id: kind === 'partner_requests' ? user : null,
        to_organization_name: kind === 'partner_requests' && i !== 1 ? 'Bühne Süd' : null,
        status:
          kind === 'team_invitations'
            ? 'invited'
            : kind === 'user_activation'
              ? 'inactive'
              : 'pending',
        has_joined: kind === 'team_invitations' ? false : null,
        created_at: '2026-09-10T08:00:00Z',
        invited_at: kind === 'team_invitations' ? '2026-09-12T08:00:00Z' : null,
        age_days: i === 2 ? null : 12 + i,
        age_basis: kind === 'team_invitations' ? 'invited_at' : 'created_at',
        action: {
          type: 'view',
          route: kind,
          entity_key,
          href: `/queues/${kind}?entity_key=${encodeURIComponent(entity_key)}`,
        },
        checks:
          i === 2
            ? [
                kind === 'team_invitations'
                  ? 'team_invitation_old'
                  : kind === 'user_activation'
                    ? 'user_activation_old'
                    : 'partner_long_pending',
              ]
            : [],
      }
    }),
  }
}
export const operationNotifications: NotificationPage = {
  ...notificationPage,
  items: ['Kulturnacht am Hafen', 'Ausstellung im Atelier', 'Konzert ohne Ortsangabe'].map(
    (name, i) => ({
      ...notification,
      id: `10000000-0000-4000-8000-00000000003${i + 1}`,
      entity_name: name,
      status: i === 1 ? 'resolved' : 'active',
      notification_type: i === 2 ? 'quality_finding' : 'unpublished_upcoming_event',
      payload: {
        ...notification.payload,
        entity_name: name,
        organization_name: 'Kulturverein Nord',
      },
      last_detected_at: stamp,
      resolved_at: i === 1 ? stamp : null,
    }),
  ),
  summary: {
    active: 18,
    queued: 3,
    sent_today: 12,
    failed: 4,
    temporary_failed: 3,
    permanent_failed: 1,
  },
  pagination: { page: 1, page_size: 25, total: 3, pages: 1 },
}
export const operationDeliveries = ['permanent_failure', 'failed', 'sent'].map((status, i) => ({
  ...notificationDelivery,
  id: `10000000-0000-4000-8000-00000000004${i + 1}`,
  status: status as 'permanent_failure' | 'failed' | 'sent',
  subject: [
    'Hinweise zur Kulturnacht',
    'Bitte Veranstaltungsangaben prüfen',
    'Neue Hinweise für euren Verein',
  ][i]!,
  organization_name: 'Kulturverein Nord',
  created_at: stamp,
  queued_at: stamp,
  sent_at: i === 2 ? stamp : null,
  next_attempt_at: i === 1 ? '2026-09-24T08:15:00Z' : null,
  last_error: i === 0 ? 'smtp_553' : i === 1 ? 'smtp_timeout' : null,
}))
export const operationDelivery: NotificationDeliveryDetail = {
  ...operationDeliveries[0]!,
  notifications: operationNotifications.items,
  retries: [],
  retry_of_delivery_id: '10000000-0000-4000-8000-000000000049',
}
export const checkOperations = {
  items: ['running', 'success', 'failed'].map((status, i) => ({
    id: `10000000-0000-4000-8000-00000000007${i}`,
    started_at: '2026-09-24T07:00:00Z',
    finished_at: i ? '2026-09-24T07:02:05Z' : null,
    status,
    rule_count: 22,
    finding_count: i === 1 ? 64 : 0,
    error_message: i === 2 ? 'Safe failure' : null,
    rule_results: {},
  })),
  pagination: { page: 1, page_size: 25, total: 3, pages: 1 },
}
export async function mockQueueOperations(page: Page) {
  await mockLayoutApi(page)
  await page.route('**/api/admin/api/v1/work-queues/**', (route) => {
    const url = new URL(route.request().url())
    const kind = url.pathname.split('/').at(-1) as QueuePage['kind']
    const fixture = queueOperations(kind)
    if (url.searchParams.get('page') === '2') fixture.pagination.page = 2
    return route.fulfill({ json: fixture })
  })
  await page.route('**/api/admin/api/v1/notifications?**', (route) =>
    route.fulfill({ json: operationNotifications }),
  )
  await page.route(`**/api/admin/api/v1/notifications/${notification.id}`, (route) =>
    route.fulfill({
      json: {
        ...operationNotifications.items[0],
        deliveries: operationDeliveries,
        delivery_enabled: false,
      },
    }),
  )
  await page.route('**/api/admin/api/v1/notifications/*/preview?**', (route) =>
    route.fulfill({ json: notificationPreview('de') }),
  )
  await page.route('**/api/admin/api/v1/notification-deliveries?**', (route) =>
    route.fulfill({
      json: {
        items: operationDeliveries,
        pagination: operationNotifications.pagination,
        delivery_enabled: false,
      },
    }),
  )
  await page.route(`**/api/admin/api/v1/notification-deliveries/${operationDelivery.id}`, (route) =>
    route.fulfill({ json: operationDelivery }),
  )
  await page.route('**/api/admin/api/v1/check-runs?**', (route) =>
    route.fulfill({ json: checkOperations }),
  )
  await page.route('**/api/admin/api/v1/admins', (route) =>
    route.fulfill({
      json: {
        items: [{ id: '10000000-0000-4000-8000-000000000090', login: 'operator' }],
        admin_timezone: 'Europe/Berlin',
      },
    }),
  )
}
