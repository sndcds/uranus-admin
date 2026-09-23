import type { QueuePage } from '../../shared/contracts'
import { entityFixture } from './entities'

export const membershipUser = entityFixture('users').items[0]!.entity_key
export const membershipOrg = '10000000-0000-4000-8000-000000000010'
export const membershipKey = `membership:${membershipOrg}:${membershipUser}`
export const membershipHref = `/queues/team_invitations?entity_key=${encodeURIComponent(membershipKey)}`
export function membershipFixture(joined: boolean): QueuePage {
  return {
    kind: 'team_invitations',
    observed_at: '2026-02-03T10:16:00Z',
    pagination: { page: 1, page_size: 50, total: 1, pages: 1 },
    items: [
      {
        entity_key: membershipKey,
        organization_id: membershipOrg,
        organization_name: 'Beispielteam',
        from_organization_id: null,
        from_organization_name: null,
        to_organization_id: null,
        to_organization_name: null,
        user_id: membershipUser,
        user_name: joined ? 'Beigetretenes Mitglied' : 'Eingeladenes Mitglied',
        status: joined ? 'joined' : 'invited',
        created_at: '2026-01-01T00:00:00Z',
        invited_at: '2026-01-02T00:00:00Z',
        has_joined: joined,
        age_days: 32,
        age_basis: 'invited_at',
        checks: [],
        action: {
          type: 'view',
          route: 'team_invitations',
          entity_key: membershipKey,
          href: membershipHref,
        },
      },
    ],
  }
}
