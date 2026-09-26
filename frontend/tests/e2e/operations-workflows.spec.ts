import { test, expect } from '../fixtures/authenticated'
import type { Page } from '@playwright/test'
import { workflowFindings, workflowInbox, workflowMarks } from '../fixtures/operations-workflows'
import { enforceProductionCsp } from '../fixtures/record-csp'
import { mockLayoutApi } from '../fixtures/layout'

async function fixtures(page: Page) {
  await enforceProductionCsp(page)
  await mockLayoutApi(page)
  await page.route('**/api/admin/api/v1/findings?*', (route) =>
    route.fulfill({ json: workflowFindings }),
  )
  await page.route('**/api/admin/api/v1/inbox?*', (route) => route.fulfill({ json: workflowInbox }))
  await page.route('**/api/admin/api/v1/record-marks**', (route) =>
    route.fulfill({
      json: new URL(route.request().url()).pathname.endsWith('/record-marks')
        ? { items: workflowMarks, pagination: { page: 1, page_size: 50, total: 4, pages: 1 } }
        : workflowMarks[0],
    }),
  )
  await page.route('**/api/admin/api/v1/admins', (route) =>
    route.fulfill({
      json: {
        items: [workflowInbox.items[1]!.assignment!.assigned_to],
        admin_timezone: 'Europe/Berlin',
      },
    }),
  )
}
async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
}

for (const [name, width, height] of [
  ['desktop', 1440, 1000],
  ['tablet', 1024, 768],
  ['mobile', 390, 844],
  ['small-mobile', 360, 800],
] as const) {
  test(`operations workflows review at ${width}px`, async ({ page }, info) => {
    test.skip(info.project.name !== 'desktop', 'Explicit viewport matrix runs once.')
    const errors: string[] = []
    page.on('pageerror', (error) => errors.push(error.message))
    await page.addInitScript(() =>
      document.addEventListener('securitypolicyviolation', (event) => {
        throw new Error(`CSP: ${event.effectiveDirective}`)
      }),
    )
    await page.setViewportSize({ width, height })
    await fixtures(page)
    const shot = async (route: string) => {
      await noOverflow(page)
      await page.screenshot({ path: info.outputPath(`${route}-${name}.png`), fullPage: true })
    }
    await page.goto('/inbox')
    await expect(
      page.getByRole('list', { name: 'Inbox-Aufgaben' }).getByRole('listitem'),
    ).toHaveCount(5)
    await expect(
      page.getByRole('region', { name: 'Inbox-Gesamtzahlen' }).getByRole('button'),
    ).toHaveCount(6)
    await expect(page.getByRole('region', { name: 'Technische Informationen' })).toContainText(
      'Europe/Berlin',
    )
    await shot('inbox')
    await page.goto('/findings')
    const table = page.getByRole('table', { name: 'Priorisierte Befunde' })
    await expect(table.locator('tbody tr')).toHaveCount(4)
    await expect(table.getByLabel('Priorität 1', { exact: true })).toBeVisible()
    await expect(table.getByRole('button')).toHaveCount(5)
    await expect(table.getByRole('button', { name: 'SQL Editor für Hafenbühne' })).toBeVisible()
    await expect(table.locator('summary')).toHaveCount(0)
    const actions = table.locator('tbody tr').nth(2).locator('td').last()
    const positions = await actions.locator('a, button').evaluateAll((elements) =>
      elements.map((element) => {
        const { top, bottom, left, height } = element.getBoundingClientRect()
        return { top, bottom, left, height }
      }),
    )
    expect(positions[1]!.top).toBeGreaterThanOrEqual(positions[0]!.bottom)
    expect(positions[1]!.left).toBe(positions[0]!.left)
    expect(positions[0]!.height).toBeGreaterThanOrEqual(44)
    await expect(table.getByRole('link')).toHaveCount(workflowFindings.items.length)
    for (const [index, finding] of workflowFindings.items.entries()) {
      await expect(
        table.locator('tbody tr').nth(index).getByRole('link', { name: 'Datensatz untersuchen' }),
      ).toHaveAttribute(
        'href',
        `/inspect/${finding.entity_type}/${encodeURIComponent(finding.entity_key)}`,
      )
    }
    await expect(page.getByRole('dialog')).toHaveCount(0)
    const summary = page.getByRole('region', { name: 'Ergebnisübersicht' })
    await expect(summary).toContainText('929 Befunde insgesamt')
    await expect(summary).toContainText('Auf dieser Seite: 4 Einträge')
    await expect(summary).toContainText('2 Fehler')
    await shot('findings')
    await page.goto('/marks')
    await expect(
      page.getByRole('list', { name: 'Markierungen' }).getByRole('listitem'),
    ).toHaveCount(4)
    await shot('marks')
    const mark = workflowMarks[0]!
    await page.goto(
      `/marks?entity_type=${mark.entity_type}&entity_key=${mark.entity_key}&status=all`,
    )
    await expect(page.getByRole('button', { name: 'Neue Markierung' })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
    await shot('marks-scoped')
    await page.goto(`/marks/${mark.id}`)
    await expect(page.getByRole('region', { name: 'Notizen und Verlauf' })).toContainText(
      'Veranstalter prüfen',
    )
    await expect(page.getByRole('region', { name: 'Technische Informationen' })).toContainText(
      'Version',
    )
    await shot('mark-detail')
    expect(errors).toEqual([])
  })
}

test('finding rows prioritize editing and keep supported tools in the workflow', async ({
  page,
}) => {
  await fixtures(page)
  await page.route('**/api/admin/api/v1/assignments?*', (route) => route.fulfill({ json: null }))
  await page.goto('/findings')
  const table = page.getByRole('table', { name: 'Priorisierte Befunde' })
  await expect(table.locator('tbody tr')).toHaveCount(4)
  await expect(table.getByRole('button', { name: /^Befund bearbeiten:/ })).toHaveCount(4)
  await expect(table.getByRole('button', { name: 'SQL Editor für Hafenbühne' })).toBeVisible()
  await expect(table.getByText('In Bearbeitung', { exact: true })).toBeVisible()
  await expect(table.getByText('Ausnahme', { exact: true })).toBeVisible()
  await table.getByRole('button', { name: 'Befund bearbeiten: Küstenkonzert' }).click()
  const first = page.getByRole('dialog', { name: 'Küstenkonzert' })
  await expect(first.getByRole('link', { name: 'Öffnen' })).toHaveCount(0)
  await page.keyboard.press('Escape')
  await table.getByRole('button', { name: 'Befund bearbeiten: Hafenbühne' }).click()
  const detail = page.getByRole('dialog', { name: 'Hafenbühne' })
  const record = detail.getByRole('link', { name: 'Öffnen' })
  await expect(record).toHaveAttribute('href', workflowFindings.items[2]!.action!.href)
  await record.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(new RegExp(workflowFindings.items[2]!.action!.href + '$'))
  await expect(page.getByRole('dialog')).toHaveCount(0)
})

test('mark conflict keeps note and history, explicit reload discards the draft', async ({
  page,
}) => {
  await fixtures(page)
  const mark = structuredClone(workflowMarks[0]!)
  mark.events[0]!.note = 'SehrLangeNotiz'.repeat(250)
  await page.route(`**/api/admin/api/v1/record-marks/${mark.id}`, (route) => {
    if (route.request().method() === 'PATCH')
      return route.fulfill({
        status: 409,
        json: { error: { code: 'mark_conflict', message: 'Conflict' } },
      })
    return route.fulfill({ json: mark })
  })
  await page.goto(`/marks/${mark.id}`)
  const note = page.getByLabel('Neue Notiz / Abschlussnotiz (optional)')
  await note.fill('Ungespeicherte Notiz')
  await page.getByRole('button', { name: 'Änderungen speichern' }).click()
  await expect(page.getByRole('alert')).toContainText('ungespeicherte Eingaben verworfen')
  await expect(note).toHaveValue('Ungespeicherte Notiz')
  await expect(page.getByRole('region', { name: 'Notizen und Verlauf' })).toContainText(
    mark.events[0]!.note!,
  )
  await noOverflow(page)
  mark.version = 2
  await page.getByRole('button', { name: 'Aktuellen Stand laden' }).click()
  await expect(note).toHaveValue('')
  await expect(
    page
      .getByRole('region', { name: 'Technische Informationen' })
      .locator('div')
      .filter({ has: page.locator('dt', { hasText: 'Version' }) })
      .last(),
  ).toContainText('2')
})

test('inbox count shortcuts, history, all task kinds and pagination use URL state', async ({
  page,
}) => {
  await fixtures(page)
  const requests: URLSearchParams[] = []
  await page.route('**/api/admin/api/v1/inbox?*', (route) => {
    const query = new URL(route.request().url()).searchParams
    requests.push(query)
    return route.fulfill({
      json: {
        ...workflowInbox,
        pagination: {
          page: Number(query.get('page') ?? 1),
          page_size: Number(query.get('page_size') ?? 25),
          total: 60,
          pages: 3,
        },
      },
    })
  })
  await page.goto('/inbox?kind=finding&page=2')
  for (const [label, key, value] of [
    ['Kritisch', 'attention', 'critical'],
    ['Meine', 'scope', 'mine'],
    ['Nicht zugewiesen', 'scope', 'unassigned'],
    ['Heute fällig', 'attention', 'due_today'],
    ['Überfällig', 'attention', 'overdue'],
    ['Wiedervorlagen', 'attention', 'snoozed'],
  ]) {
    const shortcut = page
      .getByRole('region', { name: 'Inbox-Gesamtzahlen' })
      .getByRole('button', { name: new RegExp(` ${label}$`) })
    await shortcut.click()
    await expect(shortcut).toHaveAttribute('aria-pressed', 'true')
    await expect.poll(() => requests.at(-1)?.get(key!)).toBe(value)
    expect(new URL(page.url()).searchParams.get('kind')).toBe('finding')
    expect(new URL(page.url()).searchParams.has('page')).toBe(false)
  }
  await page.goBack()
  await expect(page.getByRole('combobox', { name: 'Aufmerksamkeit', exact: true })).toHaveValue(
    'overdue',
  )
  await page.getByRole('button', { name: 'Filter zurücksetzen', exact: true }).click()
  // Reset navigates asynchronously; wait for URL and draft restoration before editing again.
  await expect(page).toHaveURL('/inbox')
  await expect(
    page.getByRole('combobox', { name: 'Aufgabenart' }).locator('option:checked'),
  ).toHaveText('Alle Aufgabenarten')
  for (const kind of ['assignment', 'finding', 'geocode_request', 'notification_delivery']) {
    await page.getByRole('combobox', { name: 'Aufgabenart' }).selectOption(kind)
    await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
    await expect.poll(() => requests.at(-1)?.get('kind')).toBe(kind)
  }
  await page.getByRole('button', { name: 'Weiter', exact: true }).click()
  await expect(page).toHaveURL(/page=2/)
  await page.getByLabel('Einträge pro Seite').selectOption('10')
  await expect(page).toHaveURL(/page_size=10/)
  expect(new URL(page.url()).searchParams.has('page')).toBe(false)
  await page.goto('/inbox?scope=mine&scope=unassigned')
  await expect(page.getByRole('alert')).toContainText('ungültige Inbox-Filter')
  await expect(page.getByRole('list', { name: 'Inbox-Aufgaben' })).toHaveCount(0)
})

for (const mode of ['live', 'persisted']) {
  test(`finding thumbnails in ${mode} mode reuse public images without per-record requests`, async ({
    page,
  }) => {
    await fixtures(page)
    const requests: string[] = []
    page.on('request', (request) => {
      if (request.url().includes('/api/admin/api/v1/'))
        requests.push(new URL(request.url()).pathname)
    })
    await page.route('**/api/admin/api/v1/findings?*', (route) =>
      route.fulfill({ json: { ...workflowFindings, mode } }),
    )
    // A missing public file must retain its row and use the type placeholder.
    await page.route(
      'https://api.kulturbytes.de/api/image/00000000-0000-4000-8000-000000000062?*',
      (route) =>
        route.fulfill({ status: 404, headers: { 'access-control-allow-origin': '*' }, body: '' }),
    )
    await page.goto(`/findings?mode=${mode}&active_only=false&page=1&page_size=50`)
    const table = page.getByRole('table', { name: 'Priorisierte Befunde' })
    await expect(table.locator('tbody tr')).toHaveCount(4)
    const image = table.getByRole('img', { name: 'Küstenkonzert' })
    await image.scrollIntoViewIfNeeded()
    await expect
      .poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth))
      .toBeGreaterThan(0)
    await expect(image).toHaveAttribute('referrerpolicy', 'no-referrer')
    await image.click()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await table.locator('tbody tr').nth(2).scrollIntoViewIfNeeded()
    await expect(
      table.locator('tbody tr').nth(2).locator('[data-compact-thumbnail] img'),
    ).toHaveCount(0)
    await expect(table.locator('[data-compact-thumbnail]')).toHaveCount(4)
    expect(
      requests.filter((path) => /\/(?:events|venues|organizations|images|users)\//.test(path)),
    ).toEqual([])
    expect(requests.filter((path) => path.endsWith('/dashboard/activity'))).toEqual([])
    await noOverflow(page)
  })
}
