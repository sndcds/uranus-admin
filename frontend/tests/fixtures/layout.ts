import type { Page } from '@playwright/test'
import { summary, findings } from './api'
import { activityFixture } from './activity'
import { statisticsFixture } from './statistics'
import { eventContentFixture } from './event-content'
import { graphFixture } from './graph'
import { entityFixture, detailFixture, timelineFixture } from './entities'
import { eventDetailFixture } from './event-detail'
import { inboxFixture } from './inbox'
import { geocodeDetail, geocodePage } from './geocoding'
import {
  notificationPage,
  notificationDetail,
  notificationDeliveryPage,
  notificationDeliveryDetail,
} from './notifications'
import {
  entitySectionSchema,
  queueKindSchema,
  type MarkDetail,
  type QueuePage,
} from '../../shared/contracts'

const stamp = '2026-09-23T07:00:00Z'
const key = '20000000-0000-4000-8000-000000000001'
export const layoutMark: MarkDetail = {
  id: '20000000-0000-4000-8000-000000000080',
  entity_type: 'event',
  entity_key: key,
  entity_name: 'Kulturnacht am Hafen',
  reasons: ['incomplete'],
  reason_detail: null,
  status: 'open',
  urgency: 'normal',
  version: 1,
  created_at: stamp,
  updated_at: stamp,
  created_by: 'admin:20000000-0000-4000-8000-000000000081',
  completed_at: null,
  completed_by: null,
  action: {
    type: 'view',
    route: 'activity',
    entity_type: 'event',
    entity_key: key,
    href: `/events/${key}`,
  },
  events: [
    {
      id: '20000000-0000-4000-8000-000000000082',
      version: 1,
      kind: 'created',
      author: 'admin:20000000-0000-4000-8000-000000000081',
      created_at: stamp,
      note: 'Bitte die Angaben mit dem Veranstalter prüfen.',
      status: 'open',
      reasons: ['incomplete'],
      reason_detail: null,
      urgency: 'normal',
    },
  ],
}
const pagination = { page: 1, pages: 1, page_size: 25, total: 1 }
function queueFixture(kind: QueuePage['kind']): QueuePage {
  return {
    kind,
    observed_at: stamp,
    pagination,
    items: [
      {
        entity_key: kind === 'user_activation' ? key : `membership:${key}:${key}`,
        organization_id: key,
        organization_name: 'Kulturverein Nord',
        from_organization_id: kind === 'partner_requests' ? key : null,
        from_organization_name: kind === 'partner_requests' ? 'Kulturverein Nord' : null,
        to_organization_id:
          kind === 'partner_requests' ? '20000000-0000-4000-8000-000000000002' : null,
        to_organization_name: kind === 'partner_requests' ? 'Bühne West' : null,
        user_id: key,
        user_name: 'Anna Beispiel',
        status: kind === 'team_invitations' ? 'invited' : 'pending',
        created_at: stamp,
        invited_at: kind === 'team_invitations' ? stamp : null,
        has_joined: kind === 'team_invitations' ? false : null,
        age_days: 0,
        age_basis: kind === 'team_invitations' ? 'invited_at' : 'created_at',
        checks: [],
        action: {
          type: 'view',
          route: 'activity',
          entity_type: 'user',
          entity_key: key,
          href: `/users/${key}`,
        },
      },
    ],
  }
}
export async function mockLayoutApi(page: Page) {
  await page.route('https://api.kulturbytes.de/**', (route) =>
    route.fulfill({
      contentType: 'image/svg+xml',
      headers: { 'access-control-allow-origin': '*' },
      body: '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="210"><rect width="320" height="210" fill="#f5d0fe"/><path d="M0 150L85 60 145 130 235 35 320 140V210H0Z" fill="#86198f"/><circle cx="60" cy="45" r="18" fill="#fdf4ff"/></svg>',
    }),
  )
  await page.route('**/api/admin/api/v1/**', (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.split('/api/v1/')[1]!
    if (path.endsWith('/timeline'))
      return route.fulfill({
        json: timelineFixture(path.split('/')[1] as Parameters<typeof timelineFixture>[0]),
      })
    const section = entitySectionSchema.options.find(
      (section) => path === section || path.startsWith(section + '/'),
    )
    if (section)
      return route.fulfill({
        json:
          path === section
            ? entityFixture(section)
            : section === 'events'
              ? eventDetailFixture()
              : detailFixture(section),
      })
    const fixed: Record<string, unknown> = {
      'dashboard/summary': summary,
      'dashboard/activity': activityFixture,
      inbox: inboxFixture,
      findings,
      'geocode/requests': geocodePage,
      [`geocode/requests/${geocodeDetail.id}`]: geocodeDetail,
      admins: { items: [], admin_timezone: 'Europe/Berlin' },
      assignments: null,
      graph: graphFixture,
      'check-runs': { items: [], pagination: { ...pagination, total: 0, pages: 0 } },
      notifications: notificationPage,
      [`notifications/${notificationDetail.id}`]: notificationDetail,
      'notification-deliveries': notificationDeliveryPage,
      [`notification-deliveries/${notificationDeliveryDetail.id}`]: notificationDeliveryDetail,
      'record-marks': { items: [layoutMark], pagination },
      [`record-marks/${layoutMark.id}`]: layoutMark,
    }
    if (Object.hasOwn(fixed, path)) return route.fulfill({ json: fixed[path] })
    if (path === 'statistics/events/content')
      return route.fulfill({ json: eventContentFixture(url.searchParams) })
    if (path === 'statistics/entities')
      return route.fulfill({ json: statisticsFixture(url.searchParams) })
    if (path.startsWith('work-queues/'))
      return route.fulfill({ json: queueFixture(queueKindSchema.parse(path.split('/')[1])) })
    return route.fulfill({
      status: 404,
      json: { error: { code: 'not_found', message: 'No layout fixture.' } },
    })
  })
}
