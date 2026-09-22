import { test, expect } from '../fixtures/authenticated'
import { inboxFixture, unassignedFindingInboxFixture } from '../fixtures/inbox'
import { geocodeDetail } from '../fixtures/geocoding'
import type { Assignment, AssignmentUpdate } from '../../shared/contracts'

// Stateful browser fixture; SQL aggregation/expiry is tested against PostgreSQL separately.
test('assign, snooze until tomorrow and unsnooze through the Inbox', async ({ page }) => {
  let assigned: Assignment | null = null
  const original = inboxFixture.items[0]!
  const admin = original.assignment!.assigned_to
  const violations: string[] = []
  page.on('pageerror', (error) => violations.push(error.message))
  await page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (event) => {
      throw new Error(`CSP violation: ${event.effectiveDirective}`)
    })
  })
  if (process.env.TEST_PRODUCTION === '1') {
    await page.route('**/*', async (route) => {
      if (route.request().resourceType() !== 'document') return route.continue()
      const response = await route.fetch()
      await route.fulfill({
        response,
        headers: {
          ...response.headers(),
          'content-security-policy':
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'",
        },
      })
    })
  }
  await page.route('**/api/admin/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (url.pathname.endsWith('/admins'))
      return route.fulfill({ json: { items: [admin], admin_timezone: 'Europe/Berlin' } })
    if (url.pathname.endsWith('/assignments') && request.method() === 'GET')
      return route.fulfill({ json: assigned })
    if (url.pathname.endsWith('/assignments') && request.method() === 'POST') {
      expect(request.postDataJSON().assigned_to_admin_id).toBe(admin.id)
      assigned = { ...original.assignment!, workflow_key: geocodeDetail.id }
      return route.fulfill({ status: 201, json: assigned })
    }
    if (url.pathname.includes('/assignments/') && request.method() === 'PATCH') {
      const patch = request.postDataJSON() as AssignmentUpdate
      expect(patch.version).toBe(assigned!.version)
      assigned = {
        ...assigned!,
        snoozed_until: patch.snoozed_until ?? null,
        version: assigned!.version + 1,
      }
      return route.fulfill({ json: assigned })
    }
    if (url.pathname.includes('/geocode/requests/')) return route.fulfill({ json: geocodeDetail })
    if (url.pathname.endsWith('/inbox')) {
      const snoozed = !!assigned?.snoozed_until
      const visible = (url.searchParams.get('attention') === 'snoozed') === snoozed
      return route.fulfill({
        json: {
          ...inboxFixture,
          items: visible
            ? [
                {
                  ...original,
                  id: assigned
                    ? `assignment:${assigned.id}`
                    : `geocode_request:${geocodeDetail.id}`,
                  kind: assigned ? 'assignment' : 'geocode_request',
                  assignment: assigned,
                  snoozed_until: assigned?.snoozed_until ?? null,
                  href: `/geocoding/${geocodeDetail.id}`,
                },
              ]
            : [],
          pagination: { page: 1, page_size: 25, total: visible ? 1 : 0, pages: visible ? 1 : 0 },
          counts: {
            critical: 0,
            mine: assigned && !snoozed ? 1 : 0,
            unassigned: assigned ? 0 : 1,
            due_today: 0,
            overdue: 0,
            snoozed: snoozed ? 1 : 0,
          },
        },
      })
    }
    return route.continue()
  })
  await page.goto('/inbox')
  await page.getByRole('link', { name: 'Vorschlag prüfen' }).click()
  await page.getByRole('button', { name: 'Mir zuweisen', exact: true }).click()
  await expect(page.getByText('Zuständigkeit gespeichert.')).toBeVisible()
  await page.getByRole('button', { name: 'Wiedervorlegen', exact: true }).click()
  const modal = page.getByRole('dialog', { name: 'Wiedervorlegen', exact: true })
  await expect(modal).toBeVisible()
  expect(await modal.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
  for (const label of ['Morgen', 'In 3 Tagen', 'Nächste Woche']) {
    const box = await modal.getByRole('button', { name: label, exact: true }).boundingBox()
    expect(box!.height).toBeGreaterThanOrEqual(44)
  }
  await modal.getByRole('button', { name: 'Morgen', exact: true }).click()
  await expect(modal).not.toBeVisible()
  await page.goto('/inbox')
  await expect(page.getByText('1 Wiedervorlagen')).toBeVisible()
  await expect(page.locator('.data-row')).toHaveCount(0)
  await page.getByRole('combobox', { name: 'Aufmerksamkeit', exact: true }).selectOption('snoozed')
  await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
  await expect(page.locator('.data-row')).toHaveCount(1)
  await expect(page.locator('.data-row time')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByRole('button', { name: 'Wiedervorlage aufheben', exact: true }).click()
  await expect(page.locator('.data-row')).toHaveCount(0)
  await page.getByRole('combobox', { name: 'Aufmerksamkeit', exact: true }).selectOption('all')
  await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
  await expect(page.locator('.data-row')).toHaveCount(1)
  await expect(page.getByText('0 Wiedervorlagen')).toBeVisible()
  expect(violations).toEqual([])
})

test('a version conflict asks for a reload and never overwrites silently', async ({ page }) => {
  let writes = 0
  await page.route('**/api/admin/api/v1/inbox?*', (route) => route.fulfill({ json: inboxFixture }))
  await page.route('**/api/admin/api/v1/assignments/*', (route) => {
    writes++
    return route.fulfill({
      status: 409,
      json: { error: { code: 'assignment_conflict', message: 'Conflict' } },
    })
  })
  await page.goto('/inbox')
  await page.getByRole('button', { name: 'Wiedervorlegen', exact: true }).click()
  const modal = page.getByRole('dialog', { name: 'Wiedervorlegen' })
  await modal.getByRole('button', { name: 'Morgen', exact: true }).click()
  await expect(modal.getByText(/zwischenzeitlich geändert/)).toBeVisible()
  await expect(modal.getByRole('button', { name: 'Morgen', exact: true })).toBeDisabled()
  expect(writes).toBe(1)
  await modal.getByRole('button', { name: 'Neu laden', exact: true }).click()
  await expect(modal).not.toBeVisible()
  expect(writes).toBe(1)
})

test('a finding review snooze has one task and directs changes to the finding', async ({
  page,
}) => {
  const until = new Date(Date.now() + 3 * 86400000).toISOString()
  const item = {
    ...unassignedFindingInboxFixture.items[0]!,
    status: 'snoozed',
    snoozed_until: until,
    finding_snoozed_until: until,
  }
  await page.route('**/api/admin/api/v1/inbox?*', (route) => {
    const visible = new URL(route.request().url()).searchParams.get('attention') === 'snoozed'
    return route.fulfill({
      json: {
        ...unassignedFindingInboxFixture,
        items: visible ? [item] : [],
        counts: { critical: 0, mine: 0, unassigned: 0, due_today: 0, overdue: 0, snoozed: 1 },
        pagination: { page: 1, page_size: 25, total: visible ? 1 : 0, pages: visible ? 1 : 0 },
      },
    })
  })
  await page.goto('/inbox')
  await expect(page.getByText('1 Wiedervorlagen')).toBeVisible()
  await expect(page.locator('.data-row')).toHaveCount(0)
  await page.goto('/inbox?attention=snoozed')
  await expect(page.locator('.data-row')).toHaveCount(1)
  await expect(page.getByText(/Fachlicher Finding-Snooze/)).toBeVisible()
  await expect(page.getByRole('link', { name: 'Finding ansehen' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Wiedervorlage aufheben' })).toHaveCount(0)
})
