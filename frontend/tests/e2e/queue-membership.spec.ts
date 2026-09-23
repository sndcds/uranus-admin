import { test, expect } from '../fixtures/authenticated'
import { detailFixture, timelineFixture } from '../fixtures/entities'
import {
  membershipFixture,
  membershipHref,
  membershipKey,
  membershipUser,
} from '../fixtures/memberships'

test.beforeEach(async ({ page }) => {
  await page.route('**/api/admin/api/v1/work-queues/team_invitations**', (route) => {
    const query = new URL(route.request().url()).searchParams
    const fixture = membershipFixture(
      ['joined', 'all'].includes(query.get('membership_status') ?? '') || !!query.get('entity_key'),
    )
    if (query.get('membership_status') === 'all' && !query.get('entity_key')) {
      const key = `membership:10000000-0000-4000-8000-000000000011:${membershipUser}`
      const invited = membershipFixture(false).items[0]!
      fixture.items.push({
        ...invited,
        organization_id: '10000000-0000-4000-8000-000000000011',
        entity_key: key,
        action: {
          ...invited.action,
          entity_key: key,
          href: `/queues/team_invitations?entity_key=${encodeURIComponent(key)}`,
        },
      })
      fixture.pagination.total = 2
    }
    return route.fulfill({ json: fixture })
  })
})

test('membership status filters support reload, back and forward', async ({ page }) => {
  await page.goto('/queues/team_invitations')
  const status = page.getByRole('combobox', { name: 'Status', exact: true })
  await expect(page.getByRole('heading', { name: 'Eingeladenes Mitglied' })).toBeVisible()
  await expect(status).toHaveValue('invited')
  await status.selectOption('joined')
  await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
  await expect(page).toHaveURL(/membership_status=joined/)
  await expect(page.getByRole('heading', { name: 'Beigetretenes Mitglied' })).toBeVisible()
  await page.reload()
  await expect(status).toHaveValue('joined')
  await status.selectOption('all')
  await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
  await expect(page).toHaveURL(/membership_status=all/)
  await expect(page.getByRole('heading', { name: 'Eingeladenes Mitglied' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Beigetretenes Mitglied' })).toBeVisible()
  await page.goBack()
  await expect(status).toHaveValue('joined')
  await expect(page.getByRole('heading', { name: 'Eingeladenes Mitglied' })).toHaveCount(0)
  await page.goForward()
  await expect(status).toHaveValue('all')
})

test('user timeline opens a joined membership directly', async ({ page }) => {
  await page.route('**/api/admin/api/v1/users/*', (route) =>
    route.fulfill({ json: detailFixture('users') }),
  )
  await page.route('**/api/admin/api/v1/entities/user/*/timeline*', (route) => {
    const fixture = timelineFixture('user')
    const item = fixture.items[0]!
    fixture.items = [
      {
        ...item,
        id: `invitation:${membershipKey}`,
        kind: 'team_invitation',
        title: 'Teameinladung',
        summary: 'Teameinladung erfasst',
        href: membershipHref,
        metadata: {
          ...item.metadata,
          status: 'joined',
          severity: null,
          rule: null,
          field: null,
          resource_id: membershipKey,
        },
      },
    ]
    return route.fulfill({ json: fixture })
  })
  await page.goto(`/users/${membershipUser}`)
  await expect(page.getByRole('heading', { name: 'Verlauf' })).toBeVisible()
  await page.getByRole('link', { name: 'Details öffnen: Teameinladung', exact: true }).click()
  await expect(page).toHaveURL(new RegExp('/queues/team_invitations\\?entity_key='))
  await expect(page.getByRole('heading', { name: 'Beigetretenes Mitglied' })).toBeVisible()
  await expect(
    page.getByText('Beigetreten', { exact: true }).filter({ visible: true }),
  ).toBeVisible()
  await expect(page.getByText('Keine Vorgänge für diese Filter.')).toHaveCount(0)
  await expect(page.getByRole('combobox', { name: 'Status', exact: true })).toBeDisabled()
  await expect(
    page.getByText('Direkt aufgerufene Teammitgliedschaft', { exact: false }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'Filter zurücksetzen', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Eingeladenes Mitglied' })).toBeVisible()
})
