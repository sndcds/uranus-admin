import { test, expect } from '@playwright/test'
import { findings } from '../fixtures/api'

const stamp = '2026-09-14T12:00:00Z'
const user = '10000000-0000-4000-8000-000000000001'
const org = '10000000-0000-4000-8000-000000000010'
const pagination = { page: 1, page_size: 50, total: 1, pages: 1 }

test('activity keeps unknown times separate and sends filters', async ({ page }) => {
  await page.route('**/api/admin/api/v1/dashboard/activity**', async (route) => {
    const unknown = new URL(route.request().url()).searchParams.get('timestamp_state') === 'unknown'
    await route.fulfill({
      json: {
        items: [
          {
            entity_type: 'image',
            entity_key: user,
            entity_name: 'Beispielbild',
            organization_id: null,
            organization_name: null,
            created_at: unknown ? null : stamp,
            status: null,
            action: null,
          },
        ],
        pagination,
        observed_at: stamp,
        from_at: unknown ? null : stamp,
        to_at: unknown ? null : stamp,
        timestamp_state: unknown ? 'unknown' : 'known',
        unknown_timestamp_count: 1,
      },
    })
  })
  await page.goto('/activity')
  await expect(page.getByRole('heading', { name: 'Beispielbild' })).toBeVisible()
  await page.getByRole('combobox', { name: 'Zeitraum', exact: true }).selectOption('unknown')
  await page.getByRole('button', { name: 'Anwenden' }).click()
  await expect(page).toHaveURL(/timestamp_state=unknown/)
  await expect(page.getByText('Nach Objektschlüssel geordnet;', { exact: false })).toBeVisible()
  await expect(
    page.getByRole('listitem').getByText('Ohne Zeitstempel', { exact: true }),
  ).toBeVisible()
})

test('queue shows actual invitation age and preserves unknown values', async ({ page }, info) => {
  await page.route('**/api/admin/api/v1/work-queues/team_invitations**', (route) =>
    route.fulfill({
      json: {
        kind: 'team_invitations',
        observed_at: stamp,
        pagination,
        items: [
          {
            entity_key: `membership:${org}:${user}`,
            organization_id: org,
            organization_name: 'Beispielteam',
            from_organization_id: null,
            from_organization_name: null,
            to_organization_id: null,
            to_organization_name: null,
            user_id: user,
            user_name: 'Eingeladener User',
            status: 'invited',
            created_at: stamp,
            invited_at: null,
            has_joined: false,
            age_days: null,
            age_basis: 'invited_at',
            checks: [],
            action: {
              type: 'view',
              route: 'team_invitations',
              entity_key: `membership:${org}:${user}`,
              href: `/queues/team_invitations?entity_key=${encodeURIComponent(`membership:${org}:${user}`)}`,
            },
          },
        ],
      },
    }),
  )
  await page.goto('/queues/team_invitations')
  await expect(page.getByRole('heading', { name: 'Eingeladener User' })).toBeVisible()
  await expect(page.getByText('Eingeladen: Nicht verfügbar', { exact: false })).toBeVisible()
  await expect(page.getByText('Alter: Nicht verfügbar', { exact: false })).toBeVisible()
  await expect(page.getByText('Eingeladen', { exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('queue.png'), fullPage: true })
  await page.getByLabel('Mindestalter (Tage)').fill('14')
  await page.getByRole('button', { name: 'Anwenden' }).click()
  await expect(page).toHaveURL(/min_age_days=14/)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Eingeladener User' })).toBeVisible()
  await expect(page.getByLabel('Mindestalter (Tage)')).toHaveValue('14')
  await page.getByRole('button', { name: 'Filter zurücksetzen', exact: true }).click()
  await expect(page).toHaveURL(/\/queues\/team_invitations$/)
  await expect(page.getByLabel('Mindestalter (Tage)')).toHaveValue('')
})

test('persisted finding accepts a reasoned exception but offers no manual resolve', async ({
  page,
}) => {
  const item = { ...findings.items[0]!, first_seen_at: stamp, status: 'open', action: null }
  await page.route('**/api/admin/api/v1/findings**', (route) =>
    route.fulfill({
      json: {
        ...findings,
        mode: 'persisted',
        items: [item],
        pagination,
      },
    }),
  )
  let body: Record<string, unknown> = {}
  await page.route('**/api/admin/api/v1/finding-reviews', (route) => {
    body = route.request().postDataJSON()
    return route.fulfill({
      json: { ...item, ...body, reviewed_at: stamp, reviewed_subject: 'development-only' },
    })
  })
  await page.goto('/findings?mode=persisted')
  await page.getByRole('button', { name: 'Befund zu Test-Hafenbühne ansehen' }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByLabel('Reviewstatus').locator('option[value="resolved"]')).toHaveCount(0)
  await dialog.getByLabel('Reviewstatus').selectOption('exception')
  await dialog.getByLabel('Ausnahmegrund').fill('Fachlich geprüfte Ausnahme')
  await dialog.getByRole('button', { name: 'Review speichern' }).click()
  await expect(dialog.getByText('Review gespeichert.')).toBeVisible()
  expect(body.status).toBe('exception')
  expect(body.exception_reason).toBe('Fachlich geprüfte Ausnahme')
})

test('real proxy keeps new admin writes authenticated', async ({ request }) => {
  expect((await request.post('/api/admin/api/v1/check-runs', { data: {} })).status()).toBe(401)
  expect(
    (
      await request.patch('/api/admin/api/v1/finding-reviews', {
        data: { finding_id: 'x', status: 'in_progress' },
      })
    ).status(),
  ).toBe(401)
  expect((await request.post('/api/admin/api/v1/work-queues/partner_requests')).status()).toBe(405)
})

test('normal finding navigation uses stored results and live diagnosis is explicit', async ({
  page,
}) => {
  const modes: string[] = []
  await page.route('**/api/admin/api/v1/findings**', (route) => {
    const mode = new URL(route.request().url()).searchParams.get('mode') ?? ''
    modes.push(mode)
    return route.fulfill({ json: { ...findings, mode } })
  })
  await page.goto('/findings')
  await expect(
    page.getByRole('button', { name: 'Befund zu Test-Hafenbühne ansehen' }),
  ).toBeVisible()
  expect(modes).toEqual(['persisted'])
  await page.getByRole('button', { name: 'Aktualisieren', exact: true }).click()
  await expect.poll(() => modes.length).toBe(2)
  expect(modes).toEqual(['persisted', 'persisted'])
  await page.getByRole('combobox', { name: 'Quelle', exact: true }).selectOption('live')
  await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
  await expect.poll(() => modes.at(-1)).toBe('live')
})
