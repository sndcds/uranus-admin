import { test, expect } from '../fixtures/authenticated'
import type { Page } from '@playwright/test'
import { workflowFindings, workflowInbox } from '../fixtures/operations-workflows'
import { mockLayoutApi } from '../fixtures/layout'
import { enforceProductionCsp } from '../fixtures/record-csp'
import { diagnosticDefinition } from '../fixtures/sql-diagnostics'
import type { Finding, ReviewUpdate } from '../../shared/contracts'

async function setup(page: Page, mode: 'persisted' | 'live' = 'persisted', item?: Finding) {
  await enforceProductionCsp(page)
  await mockLayoutApi(page)
  const items = structuredClone(item ? [item] : workflowFindings.items)
  const reviews: ReviewUpdate[] = []
  const assignmentRequests: string[] = []
  const assignment = {
    ...workflowInbox.items[1]!.assignment!,
    finding_id: items[0]!.id,
    workflow_type: null,
    workflow_key: null,
  }
  await page.route('**/api/admin/api/v1/findings?*', (route) =>
    route.fulfill({ json: { ...workflowFindings, mode, items } }),
  )
  await page.route('**/api/admin/api/v1/admins', (route) =>
    route.fulfill({ json: { items: [assignment.assigned_to], admin_timezone: 'Europe/Berlin' } }),
  )
  await page.route('**/api/admin/api/v1/assignments**', (route) => {
    assignmentRequests.push(route.request().url())
    if (route.request().method() === 'PATCH')
      Object.assign(assignment, route.request().postDataJSON(), { version: assignment.version + 1 })
    return route.fulfill({ json: assignment })
  })
  await page.route('**/api/admin/api/v1/finding-reviews', (route) => {
    const body = route.request().postDataJSON() as ReviewUpdate
    reviews.push(body)
    const finding = items.find((value) => value.id === body.finding_id)!
    Object.assign(finding, body, { reviewed_at: '2026-09-23T12:00:00Z' })
    return route.fulfill({ json: finding })
  })
  return { items, reviews, assignmentRequests }
}

for (const [name, width, height] of [
  ['desktop', 1440, 1000],
  ['tablet', 1024, 768],
  ['mobile', 390, 844],
  ['small-mobile', 360, 800],
] as const) {
  test(`findings workspace and workflow review ${width}px`, async ({ page }, info) => {
    test.skip(info.project.name !== 'desktop', 'Explicit viewport matrix runs once.')
    await page.setViewportSize({ width, height })
    await page.clock.setFixedTime(new Date('2026-09-23T12:00:00Z'))
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    await setup(page)
    await page.goto('/findings')
    const table = page.getByRole('table', { name: 'Priorisierte Befunde' })
    await expect(table.locator('tbody tr')).toHaveCount(4)
    await expect(table.locator('thead th').first()).toHaveText('Prio')
    await expect(table.locator('tbody tr').first().locator('td').first()).toHaveText('P1')
    await expect(table.getByLabel('Priorität 2', { exact: true })).toBeVisible()
    await expect(table).toContainText('Kulturverein Nord')
    await expect(table).toContainText('Enddatum liegt vor Startdatum')
    await expect(table.locator('[data-compact-thumbnail]')).toHaveCount(4)
    expect(await table.locator('thead').evaluate((e) => getComputedStyle(e).position)).toBe(
      width > 1100 ? 'sticky' : 'absolute',
    )
    expect(
      await table
        .locator('tbody tr')
        .first()
        .evaluate((e) => getComputedStyle(e).display),
    ).toBe(width > 1100 ? 'table-row' : 'grid')
    const summary = page.getByRole('region', { name: 'Ergebnisübersicht' })
    await expect(summary).toContainText('929 Befunde insgesamt')
    await expect(summary).toContainText('2 Fehler')
    await expect(summary).toContainText('auf dieser Seite')
    const tech = page.getByRole('region', { name: 'Technische Informationen' })
    await expect(tech.getByRole('heading')).toHaveCount(0)
    await expect(tech).toContainText('Client-Abrufzeit')
    await expect(page.getByRole('form', { name: 'Filter' })).toHaveClass(/p-3/)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({ path: info.outputPath(`findings-${name}.png`), fullPage: true })
    const trigger = table.getByRole('button', { name: 'Befund bearbeiten: Hafenbühne' })
    await trigger.click()
    const dialog = page.getByRole('dialog', { name: 'Hafenbühne' })
    await expect(dialog).toHaveClass(/max-w-5xl/)
    for (const heading of [
      'Evidenz',
      'Priorisierung',
      'Fachliche Bewertung',
      'Zuständigkeit',
      'Werkzeuge',
      'Technische Informationen',
    ])
      await expect(dialog.getByRole('heading', { name: heading, exact: true })).toBeVisible()
    await expect(dialog.getByLabel('Zuständig', { exact: true })).toHaveValue(
      workflowInbox.items[1]!.assignment!.assigned_to.id,
    )
    for (const label of [
      'Im Admin ansehen',
      'Standortvorschlag prüfen',
      'Beziehungen anzeigen',
      'Markierungen & Notizen',
    ])
      await expect(dialog.getByRole('link', { name: label, exact: true })).toHaveCount(1)
    await expect(dialog.getByRole('button', { name: 'SQL Editor', exact: true })).toHaveCount(1)
    await expect(dialog.getByRole('button', { name: 'Review speichern' })).toBeEnabled()
    expect(await dialog.evaluate((e) => e.scrollWidth <= e.clientWidth)).toBe(true)
    await dialog.getByRole('button', { name: 'Befund schließen' }).focus()
    await page.keyboard.press('Tab')
    expect(await dialog.evaluate((e) => e.contains(document.activeElement))).toBe(true)
    await trigger.evaluate((e) => e.focus())
    expect(await dialog.evaluate((e) => e.contains(document.activeElement))).toBe(true)
    await dialog.evaluate((e) => {
      e.scrollTop = 0
    })
    await page.screenshot({ path: info.outputPath(`finding-detail-${name}.png`) })
    await page.keyboard.press('Escape')
    await expect(trigger).toBeFocused()
    expect(errors).toEqual([])
  })
}

test('persisted review saves conditional fields, refreshes status and separates assignment snooze', async ({
  page,
}) => {
  const fixture = await setup(page, 'persisted', {
    ...workflowFindings.items[2]!,
    first_seen_at: null,
  })
  await page.goto('/findings')
  await page.getByRole('button', { name: 'Befund bearbeiten: Hafenbühne' }).click()
  const dialog = page.getByRole('dialog', { name: 'Hafenbühne' })
  await expect(dialog.getByRole('region', { name: 'Evidenz' })).toContainText('Nicht verfügbar')
  const review = dialog.getByRole('region', { name: 'Fachliche Bewertung' })
  await review.getByLabel('Reviewstatus').selectOption('exception')
  await review.getByLabel('Ausnahmegrund').fill('Fachlich begründete Ausnahme')
  await review.getByLabel('Kommentar').fill('Rücksprache mit dem Veranstalter')
  await review.getByRole('button', { name: 'Review speichern' }).click()
  await expect(review.getByRole('status')).toHaveText('Review gespeichert.')
  expect(fixture.reviews[0]).toMatchObject({
    status: 'exception',
    exception_reason: 'Fachlich begründete Ausnahme',
    snoozed_until: null,
  })
  await review.getByLabel('Reviewstatus').selectOption('snoozed')
  await expect(review.getByLabel('Ausnahmegrund')).toHaveCount(0)
  await review.getByLabel('Zurückstellen bis (Europe/Berlin)').fill('2099-07-15T09:30')
  await review.getByRole('button', { name: 'Review speichern' }).click()
  await expect.poll(() => fixture.reviews.length).toBe(2)
  expect(fixture.reviews[1]).toMatchObject({
    status: 'snoozed',
    snoozed_until: '2099-07-15T07:30:00.000Z',
    exception_reason: null,
  })
  await dialog.getByRole('button', { name: 'Wiedervorlegen', exact: true }).click()
  const snooze = page.getByRole('dialog', { name: 'Aufgabe wiedervorlegen' })
  await expect(snooze).toContainText('ändert keine fachliche Befundbewertung')
  await page.keyboard.press('Escape')
  await expect(dialog).toBeVisible()
  expect(fixture.reviews).toHaveLength(2)
  await dialog.getByRole('button', { name: 'Befund schließen' }).click()
  await expect(page.getByRole('table')).toContainText('Zurückgestellt')
})

test('live detail never loads assignments or offers review, and SQL retains live mode', async ({
  page,
}) => {
  const fixture = await setup(page, 'live')
  let sqlMode: string | null = null
  await page.route('**/api/admin/api/v1/findings/sql-diagnostic?*', (route) => {
    sqlMode = new URL(route.request().url()).searchParams.get('mode')
    return route.fulfill({ json: { ...diagnosticDefinition, last_seen_at: null } })
  })
  await page.goto('/findings?mode=live')
  await page.getByRole('button', { name: 'Befund bearbeiten: Hafenbühne' }).click()
  const dialog = page.getByRole('dialog', { name: 'Hafenbühne' })
  await expect(dialog.getByRole('region', { name: 'Evidenz' })).toBeVisible()
  await expect(dialog).toContainText('Live-Diagnose ohne gespeicherten Review')
  await expect(dialog.getByLabel('Reviewstatus')).toHaveCount(0)
  await expect(dialog.getByRole('heading', { name: 'Zuständigkeit' })).toHaveCount(0)
  await expect(dialog.getByRole('region', { name: 'Technische Informationen' })).toContainText(
    'live',
  )
  expect(fixture.assignmentRequests).toEqual([])
  await dialog.getByRole('button', { name: 'SQL Editor', exact: true }).click()
  const sql = page.getByRole('dialog', { name: 'SQL Editor', exact: true })
  await expect(sql.locator('code')).toBeVisible()
  expect(sqlMode).toBe('live')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Befund bearbeiten: Hafenbühne' })).toBeFocused()
})

test('resolved persisted finding retains evidence and tools without manual reopening', async ({
  page,
}) => {
  await setup(page, 'persisted', { ...workflowFindings.items[2]!, status: 'resolved' })
  await page.goto('/findings')
  await page.getByRole('button', { name: /^Befund bearbeiten:/ }).click()
  const dialog = page.getByRole('dialog', { name: 'Hafenbühne' })
  await expect(dialog).toContainText('Nur ein erneuter Prüflauf')
  await expect(dialog.getByRole('button', { name: 'Review speichern' })).toHaveCount(0)
  await expect(dialog.getByLabel('Zuständig', { exact: true })).toHaveCount(0)
  await expect(dialog.getByRole('button', { name: 'SQL Editor', exact: true })).toBeVisible()
})

test('desktop header remains inside the table scrollport for long pages', async ({
  page,
}, info) => {
  test.skip(info.project.name !== 'desktop', 'Desktop sticky header only.')
  await setup(page)
  await page.route('**/api/admin/api/v1/findings?*', (route) =>
    route.fulfill({
      json: {
        ...workflowFindings,
        items: Array.from({ length: 50 }, (_, index) => ({
          ...workflowFindings.items[index % 4]!,
          id: `long-page-${index}`,
        })),
      },
    }),
  )
  await page.goto('/findings')
  const scroll = page.getByRole('region', { name: 'Priorisierte Arbeitsliste scrollen' })
  const header = scroll.locator('thead')
  await expect(scroll.locator('tbody tr')).toHaveCount(50)
  await scroll.scrollIntoViewIfNeeded()
  await scroll.evaluate((e) => {
    e.scrollTop = 700
  })
  const viewport = await scroll.boundingBox(),
    head = await header.boundingBox()
  expect(Math.abs(head!.y - viewport!.y)).toBeLessThan(2)
  expect(await scroll.evaluate((e) => e.scrollWidth <= e.clientWidth)).toBe(true)
})
