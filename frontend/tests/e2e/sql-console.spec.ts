import { test, expect } from '../fixtures/authenticated'
import { findings } from '../fixtures/api'
import { diagnosticDefinition } from '../fixtures/sql-diagnostics'

async function replaceSql(page: import('@playwright/test').Page, sql: string) {
  await page.getByRole('textbox', { name: 'SQL-Abfrage bearbeiten' }).fill(sql)
}

test('console: same-origin relay, formatting, results, error, cancel and screenshots', async ({
  page,
}, info) => {
  const frames: string[] = []
  page.on('websocket', (socket) => {
    socket.on('framesent', (frame) => {
      if (socket.url().includes('/sql-console/ws'))
        frames.push(JSON.parse(String(frame.payload)).type)
    })
  })
  const errors: string[] = []
  await page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', () => {
      document.documentElement.dataset.cspViolation = 'true'
    })
  })
  page.on('pageerror', (error) => errors.push(error.message))
  if (process.env.TEST_PRODUCTION === '1') {
    // A fulfilled document loses Chromium's loopback address-space classification.
    // Permit only this local fixture origin; the production CSP remains enforced.
    await page.context().grantPermissions(['local-network-access'], {
      origin: 'http://127.0.0.1:3100',
    })
    await page.route('**/sql', async (route) => {
      const response = await route.fetch()
      await route.fulfill({
        response,
        headers: {
          ...response.headers(),
          'content-security-policy':
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'",
        },
      })
    })
  }
  await page.goto('/sql')
  await expect(page.getByRole('textbox', { name: 'SQL-Abfrage bearbeiten' })).toBeVisible()
  expect((await page.locator('.sql-code').boundingBox())!.height).toBeGreaterThanOrEqual(420)
  const screenshot = async (name: string) => {
    if (info.project.name === 'desktop' && process.env.TEST_PRODUCTION === '1')
      await expect(page.locator('.sql-workspace')).toHaveScreenshot(name, {
        animations: 'disabled',
        maxDiffPixelRatio: 0.001,
      })
    await page.screenshot({ path: info.outputPath(name), fullPage: true })
    await info.attach(name, { path: info.outputPath(name), contentType: 'image/png' })
  }
  await screenshot('sql-console.png')
  await replaceSql(
    page,
    'SELECT uuid,event_uuid,start_date FROM uranus_console.event_date WHERE uuid=:entity_key LIMIT 50',
  )
  await page.getByRole('button', { name: 'SQL formatieren', exact: true }).click()
  await expect(page.locator('.cm-line').first()).toHaveText('SELECT')
  await expect(page.locator('.cm-line').nth(1)).toHaveText('    uuid,')
  await replaceSql(
    page,
    'SELECT uuid,event_uuid,start_date,start_time,end_date,end_time FROM uranus_console.event_date LIMIT 50;',
  )
  await page.getByRole('button', { name: 'SQL formatieren', exact: true }).click()
  await page.getByRole('button', { name: 'Abfrage ausführen', exact: true }).click()
  await expect(page.getByText('Completed', { exact: true })).toBeVisible()
  await expect(page.getByText('verbunden', { exact: true })).toBeVisible()
  await expect(page.getByRole('table', { name: 'Diagnose-Ergebnis' })).toContainText('2026-10-12')
  await screenshot('sql-results.png')
  await page.getByRole('button', { name: 'JSON', exact: true }).click()
  await expect(page.locator('.language-json .property').first()).toBeVisible()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Als CSV herunterladen' }).click()
  expect((await download).suggestedFilename()).toBe('sql-ergebnis.csv')
  await replaceSql(page, 'SELECT fixture_error;')
  await page.keyboard.press('Control+Enter')
  await expect(page.getByRole('alert')).toContainText('SQL-Syntax')
  await expect(page.locator('.sql-error-position')).toBeVisible()
  await screenshot('sql-error.png')
  await replaceSql(
    page,
    'SELECT sum(i)\nFROM generate_series(1, 1000000000) AS i;\n-- fixture_running',
  )
  await page.keyboard.press('Control+Enter')
  await expect(page.getByText('Running', { exact: true })).toBeVisible()
  await screenshot('sql-running-cancel.png')
  await page.getByRole('button', { name: 'Abbrechen', exact: true }).click()
  await expect.poll(() => frames).toContain('cancel')
  await expect(page.getByText('Cancelled', { exact: true })).toBeVisible()
  expect(errors).toEqual([])
  await expect(page.locator('html')).not.toHaveAttribute('data-csp-violation', 'true')
})

test('finding: readonly/editable parity and Escape cancels before closing', async ({
  page,
}, info) => {
  const finding = { ...findings.items[0]!, sql_diagnostic_available: true }
  const sql =
    "SELECT :entity_key, 123.45, 'text'::text, COUNT(*), ST_X(point), COALESCE(title, 'x')\nFROM uranus_console.event AS e\nLEFT JOIN uranus_console.event_date AS d ON e.uuid = d.event_uuid\nWHERE e.uuid IS NOT NULL AND TRUE OR FALSE\n-- comment\n/* comment */"
  await page.route('**/api/admin/api/v1/findings**', (route) =>
    route.fulfill({
      json: route.request().url().includes('sql-diagnostic')
        ? { ...diagnosticDefinition, sql, console_sql: sql }
        : { ...findings, items: [finding] },
    }),
  )
  await page.goto('/findings')
  await page.getByRole('button', { name: `SQL Editor für ${finding.entity_name}` }).click()
  const dialog = page.getByRole('dialog', { name: 'SQL Editor', exact: true })
  await expect(dialog.locator('.token.keyword').first()).toBeVisible()
  const sample = async () =>
    page.locator('.sql-code').evaluate((element) => {
      const style = getComputedStyle(element)
      return {
        gutterWidth: element.querySelector('.sql-gutter, .cm-gutters')!.getBoundingClientRect()
          .width,
        textOffset:
          element.querySelector('.token')!.getBoundingClientRect().x -
          element.getBoundingClientRect().x,
        background: style.backgroundColor,
        font: style.fontFamily,
        fontSize: style.fontSize,
        lineHeight: style.lineHeight,
        tokens: Array.from(element.querySelectorAll('.token')).map((token) => ({
          text: token.textContent,
          color: getComputedStyle(token).color,
          class: token.className,
        })),
      }
    })
  const readonly = await sample()
  if (info.project.name === 'desktop')
    await expect(dialog.locator('.sql-code')).toHaveScreenshot('sql-theme-parity.png', {
      maxDiffPixelRatio: 0.001,
    })
  if (info.project.name === 'desktop' && process.env.TEST_PRODUCTION === '1')
    await expect(dialog).toHaveScreenshot('finding-readonly.png', { maxDiffPixelRatio: 0.001 })
  await page.screenshot({ path: info.outputPath('finding-readonly.png'), fullPage: true })
  await dialog.getByRole('button', { name: 'SQL bearbeiten', exact: true }).click()
  await expect(dialog.locator('.cm-editor')).toBeVisible()
  await expect(dialog.locator('.token.parameter').first()).toBeVisible()
  expect(await sample()).toEqual(readonly)
  if (info.project.name === 'desktop')
    await expect(dialog.locator('.sql-code')).toHaveScreenshot('sql-theme-parity.png', {
      maxDiffPixelRatio: 0.001,
    })
  if (info.project.name === 'desktop' && process.env.TEST_PRODUCTION === '1')
    await expect(dialog).toHaveScreenshot('finding-editable.png', { maxDiffPixelRatio: 0.001 })
  await page.screenshot({ path: info.outputPath('finding-editable.png'), fullPage: true })
  await replaceSql(page, 'SELECT 1 -- fixture_running')
  await expect(dialog.getByText('Benutzerdefinierte Abfrage', { exact: true })).toBeVisible()
  await page.keyboard.press('Control+Enter')
  await expect(dialog.getByText('Running', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(dialog).toBeVisible()
  await expect(dialog.getByText('Cancelled', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(dialog).not.toBeVisible()
})
