import { test, expect } from '../fixtures/authenticated'
import { summary, findings } from '../fixtures/api'

const rule = 'membership_joined_accept_token_present'

test('internal membership integrity has readable label and safe organization action', async ({
  page,
}) => {
  const key = findings.items[0]!.entity_key
  let filters: URLSearchParams | undefined
  await page.route('**/api/admin/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/summary'))
      return route.fulfill({
        json: {
          ...summary,
          quality: {
            total: 1,
            errors: 1,
            warnings: 0,
            info: 0,
            rules: [rule],
            rule_counts: { [rule]: 1 },
            mode: 'persisted',
          },
        },
      })
    if (url.pathname.endsWith('/findings')) {
      filters = url.searchParams
      return route.fulfill({
        json: {
          ...findings,
          mode: 'persisted',
          items: [
            {
              ...findings.items[0],
              id: `${rule}:team_membership:synthetic:accept_token`,
              rule,
              field: 'accept_token',
              entity_type: 'team_membership',
              entity_key: `membership:${key}:${key}`,
              entity_id: null,
              entity_name: 'Synthetische Mitgliedschaft',
              severity: 'error',
              priority: 3,
              priority_score: 4000,
              priority_reasons: ['severity_error'],
              address: {},
              upcoming_event_date_count: 0,
              upcoming_published_event_date_count: 0,
              soon_published_event_date_count: 0,
              message:
                'Eine bereits angenommene Team-Einladung besitzt noch einen aktiven Einladungstoken.',
              metadata: { token_present: true, category: 'security' },
              action: {
                type: 'view',
                route: 'activity',
                entity_type: 'organization',
                entity_key: key,
                href: `/organizations/${key}`,
              },
            },
          ],
          pagination: { page: 1, page_size: 50, total: 1, pages: 1 },
        },
      })
    }
    return route.fulfill({ json: {} })
  })
  await page.goto('/quality')
  await expect(page.getByRole('heading', { name: 'Interne Sicherheit' })).toBeVisible()
  await page.getByRole('link', { name: /Einladungstoken nach Beitritt vorhanden/ }).click()
  const list = page.getByRole('table', { name: 'Priorisierte Befunde', exact: true })
  await expect(list).toContainText('Eine bereits angenommene Team-Einladung')
  await expect(list.getByRole('link', { name: 'Im Admin ansehen' })).toHaveAttribute(
    'href',
    `/organizations/${key}`,
  )
  expect(filters?.get('rule')).toBe(rule)
  expect(filters?.get('entity_type')).toBe('team_membership')
  expect(filters?.get('mode')).toBe('persisted')
  await expect(list.getByRole('button', { name: /ansehen/ })).toHaveCount(0)
  await expect(page.getByRole('dialog')).toHaveCount(0)
  await expect(list).toContainText('Einladungstoken')
  await expect(list).not.toContainText('"token_present":')
})
