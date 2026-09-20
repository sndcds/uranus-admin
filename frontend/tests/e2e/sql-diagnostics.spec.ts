import { test, expect } from '../fixtures/authenticated'
import { findings, summary } from '../fixtures/api'
import { diagnosticDefinition, diagnosticResult } from '../fixtures/sql-diagnostics'

import { formatPostgresql } from '../../app/utils/sql-formatter'
const supportedFinding = {
  ...findings.items[0]!,
  id: 'venue_missing_location:venue:00000000-0000-4000-8000-000000000020:point',
  rule: diagnosticDefinition.recipe_id,
  first_seen_at: diagnosticDefinition.last_seen_at,
  sql_diagnostic_available: true,
}

for (const path of ['/', '/findings']) {
  test(`SQL Editor from ${path}: lazy, read-only, copy, execute, focus and reset`, async ({
    page,
  }, testInfo) => {
    let definitions = 0
    let executions = 0
    const browserErrors: string[] = []
    page.on('pageerror', (error) => browserErrors.push(error.message))
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
    await page.addInitScript(() => {
      const state = window as typeof window & { sqlCspViolations: string[] }
      state.sqlCspViolations = []
      document.addEventListener('securitypolicyviolation', (event) => {
        state.sqlCspViolations.push(`${event.effectiveDirective}: ${event.blockedURI}`)
      })
      Object.defineProperty(navigator, 'clipboard', {
        configurable: true,
        value: {
          writeText: async (text: string) => {
            ;(window as typeof window & { copiedSql?: string }).copiedSql = text
          },
        },
      })
    })
    await page.route('**/api/admin/api/v1/**', async (route) => {
      const url = new URL(route.request().url())
      if (url.pathname.endsWith('/sql-diagnostic/execute')) {
        executions++
        expect(route.request().postDataJSON()).toEqual({ finding_id: supportedFinding.id })
        return route.fulfill({
          json: {
            ...diagnosticResult,
            rows: diagnosticResult.rows.map((row) => ({ ...row, point_missing: false })),
            evaluation: {
              ...diagnosticResult.evaluation,
              matched: false,
              message: 'Aktueller Datenstand erfüllt die Regel nicht mehr.',
              checks: diagnosticResult.evaluation.checks.map((check) => ({
                ...check,
                value: false,
              })),
            },
          },
        })
      }
      if (url.pathname.endsWith('/sql-diagnostic')) {
        definitions++
        expect(url.searchParams.get('finding_id')).toBe(supportedFinding.id)
        return route.fulfill({ json: diagnosticDefinition })
      }
      if (url.pathname.endsWith('/dashboard/summary')) return route.fulfill({ json: summary })
      return route.fulfill({
        json: {
          ...findings,
          mode: 'persisted',
          items: [
            {
              ...supportedFinding,
              status: path === '/findings' ? 'resolved' : 'open',
            },
            {
              ...findings.items[0],
              id: 'unsupported',
              entity_name: 'Unsupported',
              sql_diagnostic_available: false,
            },
          ],
        },
      })
    })
    await page.goto(path)
    const trigger = page.getByRole('button', { name: 'SQL Editor für Test-Hafenbühne' })
    await expect(trigger).toBeVisible()
    expect(definitions).toBe(0)
    expect(executions).toBe(0)
    await expect(page.getByRole('button', { name: 'SQL Editor für Unsupported' })).toHaveCount(0)
    await trigger.click()
    const dialog = page.getByRole('dialog', { name: 'SQL Editor', exact: true })
    await expect(dialog).toBeVisible()
    await expect(dialog).toHaveClass(/max-w-5xl/)
    await expect(dialog.getByText('READ ONLY')).toBeVisible()
    await expect(dialog.locator('.token.keyword').first()).toBeVisible()
    await expect(dialog.locator('code')).toHaveText(formatPostgresql(diagnosticDefinition.sql))
    await expect(dialog.getByRole('table', { name: 'Gebundene SQL-Parameter' })).toContainText(
      'UUID',
    )
    expect(executions).toBe(0)
    // Native modal navigation and inert background (browser chrome can still take focus).
    await dialog.getByRole('button', { name: 'SQL Editor schließen' }).focus()
    await page.keyboard.press('Tab')
    await expect(dialog.getByRole('button', { name: 'SQL Editor', exact: true })).toBeFocused()
    await page.keyboard.press('Shift+Tab')
    await expect(dialog.getByRole('button', { name: 'SQL Editor schließen' })).toBeFocused()
    await trigger.evaluate((element) => element.focus())
    expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true)
    await dialog.getByRole('button', { name: 'SQL kopieren', exact: true }).click()
    await expect(dialog.getByText('SQL kopiert', { exact: true })).toBeVisible()
    expect(
      await page.evaluate(() => (window as typeof window & { copiedSql?: string }).copiedSql),
    ).toBe(formatPostgresql(diagnosticDefinition.copy_sql))
    await dialog.getByRole('button', { name: 'Abfrage ausführen', exact: true }).click()
    await expect(
      dialog.getByText('Der aktuelle Datenstand erfüllt diese Regel nicht mehr.'),
    ).toBeVisible()
    expect(executions).toBe(1)
    await expect(dialog.getByRole('table', { name: 'Diagnose-Ergebnis' })).toContainText(
      'point_missing',
    )
    await dialog.getByRole('button', { name: 'JSON', exact: true }).click()
    await expect(dialog.locator('.language-json .property').first()).toBeVisible()
    await expect(dialog.locator('.language-json')).toContainText('point_missing')
    await dialog.getByRole('button', { name: 'Tabellarisch', exact: true }).click()
    const download = page.waitForEvent('download')
    await dialog.getByRole('button', { name: 'Als CSV herunterladen' }).click()
    expect((await download).suggestedFilename()).toBe('sql-ergebnis.csv')
    expect(executions).toBe(1)
    await expect(dialog.getByText('TOP-SECRET-FIXTURE')).toHaveCount(0)
    expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(
      true,
    )
    if (path === '/findings') {
      if (testInfo.project.name === 'desktop')
        await page.setViewportSize({ width: 1536, height: 1024 })
      await expect(dialog.getByText('SQL kopiert', { exact: true })).toHaveCount(0)
      await dialog.evaluate((element) => {
        element.scrollTop = 0
      })
      await page.screenshot({ path: testInfo.outputPath('sql-editor-modal.png') })
      await testInfo.attach('SQL Editor Modal', {
        path: testInfo.outputPath('sql-editor-modal.png'),
        contentType: 'image/png',
      })
    }
    await page.keyboard.press('Escape')
    await expect(dialog).not.toBeVisible()
    await expect(trigger).toBeFocused()
    await trigger.click()
    await expect(dialog.getByText('Noch keine Abfrage ausgeführt.')).toBeVisible()
    await expect(dialog.getByRole('table', { name: 'Diagnose-Ergebnis' })).toHaveCount(0)
    await dialog.getByRole('button', { name: 'SQL Editor schließen' }).click()
    await expect(trigger).toBeFocused()
    expect(browserErrors).toEqual([])
    expect(
      await page.evaluate(
        () => (window as typeof window & { sqlCspViolations: string[] }).sqlCspViolations,
      ),
    ).toEqual([])
  })
}

test('SQL Editor follows the mockup and reopens the finding through its new-tab link', async ({
  page,
  context,
}, testInfo) => {
  // Synthetic UI fixture using the columns of the registered event-date recipe.
  const entityKey = '00000000-0000-4000-8000-000000000030'
  const finding = {
    ...supportedFinding,
    id: `event_date_end_before_start:event_date:${entityKey}:end_date`,
    rule: 'event_date_end_before_start',
    entity_type: 'event_date',
    entity_key: entityKey,
    entity_name: 'Kürbismenü',
    severity: 'error',
    field: 'end_date',
    message: 'Das Enddatum liegt vor dem Startdatum.',
    organization_name: 'Figaro Hotelbetrieb GmbH & Co. KG',
    last_seen_at: '2026-09-20T09:29:00Z',
  }
  const sql =
    'SELECT uuid,event_uuid,start_date,start_time,end_date,end_time,all_day,release_status::text FROM uranus.event_date WHERE uuid = :entity_key LIMIT :diagnostic_limit'
  const definition = {
    ...diagnosticDefinition,
    recipe_id: finding.rule,
    title: 'Enddatum liegt vor Startdatum',
    sql,
    copy_sql: sql.replace(':entity_key', `'${entityKey}'`).replace(':diagnostic_limit', '50'),
    parameters: { entity_key: entityKey, diagnostic_limit: 50 },
    columns: [
      'uuid',
      'event_uuid',
      'start_date',
      'start_time',
      'end_date',
      'end_time',
      'all_day',
      'release_status',
    ],
    explanation: 'Enddatum vorhanden und Enddatum < Startdatum.',
  }
  await context.route('**/api/admin/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/sql-diagnostic/execute')) {
      expect(route.request().postDataJSON()).toEqual({ finding_id: finding.id })
      return route.fulfill({
        json: {
          ...diagnosticResult,
          recipe_id: finding.rule,
          columns: definition.columns,
          duration_ms: 14,
          rows: [
            {
              uuid: entityKey,
              event_uuid: '00000000-0000-4000-8000-000000000031',
              start_date: '2026-10-12',
              start_time: '18:00:00',
              end_date: '2026-10-11',
              end_time: '17:00:00',
              all_day: false,
              release_status: 'published',
            },
          ],
          evaluation: {
            ...diagnosticResult.evaluation,
            checks: [
              {
                label: 'Enddatum < Startdatum',
                value: true,
                left: '2026-10-11',
                operator: '<',
                right: '2026-10-12',
              },
            ],
          },
        },
      })
    }
    if (url.pathname.endsWith('/sql-diagnostic')) return route.fulfill({ json: definition })
    return route.fulfill({ json: { ...findings, mode: 'persisted', items: [finding] } })
  })
  if (testInfo.project.name === 'desktop') await page.setViewportSize({ width: 1536, height: 1024 })
  await page.goto('/findings')
  await page.getByRole('button', { name: 'SQL Editor für Kürbismenü' }).click()
  const dialog = page.getByRole('dialog', { name: 'SQL Editor', exact: true })
  await expect(dialog.locator('code')).toHaveText(formatPostgresql(sql))
  await dialog.getByRole('button', { name: 'Abfrage ausführen', exact: true }).click()
  await expect(dialog.getByRole('table', { name: 'Diagnose-Ergebnis' })).toContainText('published')
  const sidebar = await dialog.locator('aside').boundingBox()
  const main = await dialog.locator('main').boundingBox()
  if (testInfo.project.name === 'desktop') {
    expect(sidebar!.width).toBe(260)
    expect(main!.x).toBe(sidebar!.x + sidebar!.width)
    expect(Math.abs(main!.y - sidebar!.y)).toBeLessThan(1)
  } else expect(main!.y).toBeGreaterThan(sidebar!.y + sidebar!.height - 1)
  const sqlBox = await dialog
    .getByRole('region', { name: 'SQL-Abfrage, Nur-Lese-Modus' })
    .boundingBox()
  const parameters = await dialog
    .getByRole('table', { name: 'Gebundene SQL-Parameter' })
    .boundingBox()
  const result = await dialog.getByRole('table', { name: 'Diagnose-Ergebnis' }).boundingBox()
  expect(parameters!.y).toBeGreaterThan(sqlBox!.y + sqlBox!.height)
  expect(result!.y).toBeGreaterThan(parameters!.y + parameters!.height)
  expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(
    true,
  )
  await dialog.evaluate((element) => {
    element.scrollTop = 0
  })
  await page.screenshot({ path: testInfo.outputPath('sql-editor-modal.png') })
  await testInfo.attach('SQL Editor Mockup', {
    path: testInfo.outputPath('sql-editor-modal.png'),
    contentType: 'image/png',
  })
  const popupEvent = page.waitForEvent('popup')
  await dialog.getByRole('link', { name: 'SQL Editor in neuem Tab öffnen' }).click()
  const popup = await popupEvent
  await expect(popup.getByRole('dialog', { name: 'SQL Editor', exact: true })).toBeVisible()
  await expect(popup.locator('dialog aside')).toContainText('Kürbismenü')
  await expect(popup.locator('dialog code')).toHaveText(formatPostgresql(sql))
  await popup.close()
})
