import { test, expect } from '../fixtures/authenticated'
import { graphFixture, graphPath } from '../fixtures/graph'

const sizes = [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'tablet', width: 1024, height: 768 },
  { name: 'mobile', width: 390, height: 844 },
  { name: 'small', width: 360, height: 800 },
]
const screenshotOptions = {
  fullPage: true,
  animations: 'disabled',
  caret: 'hide',
  style: '.cm-cursor, .cm-dropCursor { visibility: hidden !important; }',
} as const

for (const size of sizes) {
  test(`graph operations workspace ${size.width}`, async ({ page }, info) => {
    test.skip(info.project.name !== 'desktop', 'Explicit viewport matrix runs once')
    await page.setViewportSize(size)
    await page.route('**/api/admin/api/v1/graph**', (route) => {
      const url = new URL(route.request().url())
      if (url.pathname.endsWith('/search'))
        return route.fulfill({ json: { items: [graphFixture.nodes[0]] } })
      return route.fulfill({ json: graphFixture })
    })
    await page.goto('/graph')
    await expect(page.getByRole('heading', { name: 'Datensatz auswählen' })).toBeVisible()
    await expect(page.locator('.graph-canvas')).toHaveCount(0)
    if (size.name === 'desktop')
      await page.screenshot({
        ...screenshotOptions,
        path: info.outputPath('graph-empty-desktop.png'),
      })
    await page.getByLabel('Nach Name, E-Mail oder UUID suchen', { exact: true }).fill('Rendsburg')
    await page
      .getByRole('button', { name: 'Kulturzentrum Rendsburg e.V. Organisation', exact: true })
      .click()
    const root = page.locator('.graph-node').first()
    await expect(root).toBeFocused()
    await expect(root).toHaveAttribute('aria-pressed', 'true')
    const workspace = page.locator('.graph-workspace')
    const inspector = page.getByRole('complementary', { name: 'Knotendetails' })
    const footer = workspace.getByRole('region', { name: 'Technische Informationen' })
    await expect(footer).toContainText('12 sichtbar / 12 geladen')
    await expect(footer).toContainText(graphFixture.root.key)
    await expect(footer.getByRole('heading')).toHaveCount(0)
    await expect(inspector.getByRole('link', { name: 'Markierungen & Notizen' })).toHaveAttribute(
      'href',
      /entity_type=organization/,
    )
    const canvasBox = (await page.locator('.graph-canvas').boundingBox())!
    const inspectorBox = (await inspector.boundingBox())!
    if (size.width >= 1280) {
      expect(canvasBox.width).toBeGreaterThan(inspectorBox.width * 2)
      expect(Math.abs(canvasBox.y - inspectorBox.y)).toBeLessThan(1)
    } else expect(inspectorBox.y).toBeGreaterThanOrEqual(canvasBox.y + canvasBox.height - 1)
    await page.getByRole('button', { name: 'Darstellung', exact: true }).click()
    await expect(page.getByLabel('Beziehungen beschriften', { exact: true })).toBeChecked()
    await page.getByLabel('Beziehungen beschriften', { exact: true }).uncheck()
    await expect(
      page.locator('.graph-canvas text').filter({ hasText: 'Mitglied von' }),
    ).toHaveCount(0)
    await page.getByRole('button', { name: 'Darstellung', exact: true }).click()
    await page.getByRole('button', { name: 'Zurücksetzen', exact: true }).click()
    await expect(
      page.locator('.graph-canvas text').filter({ hasText: 'Mitglied von' }),
    ).toHaveCount(2)
    await page.getByLabel('Maximale Tiefe').selectOption('3')
    await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
    await expect(page).toHaveURL(/depth=3/)
    await expect(footer).toContainText('Tiefe3')
    await page.getByRole('button', { name: 'Zurücksetzen', exact: true }).click()
    await expect(page).toHaveURL(/depth=2/)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    for (const button of await inspector.getByRole('button').all()) {
      const box = await button.boundingBox()
      if (box) expect(box.height).toBeGreaterThanOrEqual(44)
    }
    await page.screenshot({ ...screenshotOptions, path: info.outputPath(`graph-${size.name}.png`) })
  })

  test(`sql operations workspace ${size.width}`, async ({ page }, info) => {
    test.skip(info.project.name !== 'desktop', 'Explicit viewport matrix runs once')
    await page.setViewportSize(size)
    await page.goto('/sql')
    const editor = page.getByRole('textbox', { name: 'SQL-Abfrage bearbeiten' })
    const context = page.getByRole('complementary', { name: 'Datenbankkontext' })
    const footer = page.getByRole('region', { name: 'Technische Informationen' })
    await expect(editor).toContainText('FROM uranus.event')
    await expect(context).toContainText('READ ONLY')
    await expect(context.getByRole('status')).toContainText('getrennt')
    await expect(page.getByText('Bereit', { exact: true })).toBeVisible()
    await expect(footer).toContainText('Query timeout5s')
    await expect(footer).toContainText('Row limit500')
    await expect(footer).toContainText('Gesamtdeadline8s')
    await expect(page.getByRole('main')).toHaveCount(1)
    const codeBox = (await page.locator('.sql-code').boundingBox())!
    const contextBox = (await context.boundingBox())!
    if (size.width >= 1280) expect(codeBox.width).toBeGreaterThan(contextBox.width * 3)
    else expect(codeBox.y).toBeGreaterThan(contextBox.y + contextBox.height)
    for (const control of await page
      .locator('.sql-workspace button, .sql-workspace select')
      .all()) {
      const box = await control.boundingBox()
      if (box) expect(box.height).toBeGreaterThanOrEqual(44)
    }
    await page.screenshot({ ...screenshotOptions, path: info.outputPath(`sql-${size.name}.png`) })
    await editor.fill('SELECT 1 -- fixture_running')
    await page.keyboard.press('Control+Enter')
    await expect(page.getByText('Wird ausgeführt', { exact: true })).toBeVisible()
    await expect(context.getByRole('status')).toContainText('verbunden')
    await expect(page.getByRole('button', { name: 'Abfrage ausführen' })).toBeDisabled()
    if (size.name === 'desktop')
      await page.screenshot({
        ...screenshotOptions,
        path: info.outputPath('sql-running-desktop.png'),
      })
    await page.getByRole('button', { name: 'Abbrechen', exact: true }).focus()
    await page.keyboard.press('Enter')
    await expect(page.getByText('Abgebrochen', { exact: true })).toBeVisible()
    await editor.fill('SELECT uuid, event_uuid, start_date FROM uranus.event_date LIMIT 50;')
    await page.keyboard.press('Control+Enter')
    await expect(page.getByText('Abgeschlossen', { exact: true })).toBeVisible()
    const result = page.getByRole('region', { name: 'Ergebnistabelle' })
    await expect(result.getByRole('table')).toContainText('2026-10-12')
    await expect(result).toHaveAttribute('tabindex', '0')
    await expect(result.getByRole('table')).toHaveAccessibleName('Diagnose-Ergebnis')
    if (size.name === 'desktop')
      await page.screenshot({
        ...screenshotOptions,
        path: info.outputPath('sql-result-desktop.png'),
      })
    // A long unbroken identifier stays inside the editor's scrollport.
    await editor.fill(`SELECT ${'synthetic_column_'.repeat(70)};`)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await editor.fill('SELECT fixture_error;')
    await page.keyboard.press('Control+Enter')
    await expect(page.getByRole('alert')).toContainText('SQL-Syntax')
    await expect(page.getByRole('alert')).toContainText('SQL-Position: 8')
    if (size.name === 'desktop')
      await page.screenshot({
        ...screenshotOptions,
        path: info.outputPath('sql-error-desktop.png'),
      })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}

test('graph same-selection refresh stays visible; new root clears before response', async ({
  page,
}) => {
  await page.route('**/api/admin/api/v1/graph?**', (route) => route.fulfill({ json: graphFixture }))
  await page.goto(graphPath)
  await expect(page.locator('.graph-node')).toHaveCount(12)
  let release!: () => void
  const held = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route('**/api/admin/api/v1/graph?**', async (route) => {
    await held
    const url = new URL(route.request().url())
    await route.fulfill({
      json: {
        ...graphFixture,
        root: {
          type: url.searchParams.get('root_type'),
          key: url.searchParams.get('root_key'),
        },
      },
    })
  })
  await page.getByRole('button', { name: 'Aktualisieren', exact: true }).click()
  await expect(page.getByText('Daten werden aktualisiert …', { exact: true })).toBeVisible()
  await expect(page.locator('.graph-node')).toHaveCount(12)
  await page.locator('.graph-node').filter({ hasText: 'Max Mustermann' }).click()
  await page
    .getByRole('complementary', { name: 'Knotendetails' })
    .getByRole('button', { name: 'Beziehungen', exact: true })
    .click()
  await expect(page.locator('.graph-node')).toHaveCount(0)
  release()
  await expect(page.locator('.graph-node')).toHaveCount(12)
  await expect(
    page.getByRole('complementary', { name: 'Knotendetails' }).getByRole('heading'),
  ).toHaveText('Max Mustermann')
  await expect(page.locator(`.graph-node[data-id="${graphFixture.nodes[1]!.id}"]`)).toHaveAttribute(
    'aria-pressed',
    'true',
  )
})

test('SQL empty, truncation, timeout and disconnect are distinct; wide results scroll locally', async ({
  page,
}) => {
  let mode: 'empty' | 'rows' | 'timeout' = 'empty'
  let closeSocket!: () => void
  await page.routeWebSocket('**/sql-console/ws', (socket) => {
    closeSocket = () => socket.close()
    socket.onMessage((raw) => {
      const message = JSON.parse(String(raw)) as {
        type: string
        request_id: string
        row_limit?: number
      }
      const send = (body: Record<string, unknown>) =>
        socket.send(JSON.stringify({ v: 1, request_id: message.request_id, ...body }))
      if (message.type === 'ack') {
        send({ type: 'complete', row_count: 1, truncated: true, duration_ms: 4 })
        return
      }
      if (message.type !== 'execute') return
      if (mode === 'timeout') {
        send({ type: 'error', code: 'timeout', duration_ms: 5000 })
        return
      }
      send({
        type: 'columns',
        columns: Array.from({ length: 12 }, (_, i) => `synthetic_column_${i}`),
      })
      if (mode === 'empty') {
        send({ type: 'complete', row_count: 0, truncated: false, duration_ms: 2 })
        return
      }
      expect(message.row_limit).toBe(500)
      send({
        type: 'rows',
        batch: 1,
        rows: [
          Object.fromEntries(
            Array.from({ length: 12 }, (_, i) => [
              `synthetic_column_${i}`,
              'long synthetic value '.repeat(10),
            ]),
          ),
        ],
      })
    })
  })
  await page.goto('/sql')
  await page.getByRole('button', { name: 'Abfrage ausführen', exact: true }).click()
  await expect(
    page.getByText('Die Abfrage hat keine aktuellen Datensätze zurückgegeben.'),
  ).toBeVisible()
  mode = 'rows'
  await page.getByLabel('Zeilenlimit').selectOption('500')
  await page.getByRole('button', { name: 'Abfrage ausführen', exact: true }).click()
  const result = page.getByRole('region', { name: 'Ergebnistabelle' })
  await expect(
    page.getByText('Inspektionsgrenze erreicht; möglicherweise weitere Zeilen vorhanden.'),
  ).toBeVisible()
  expect(await result.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true)
  await result.focus()
  await page.keyboard.press('ArrowRight')
  await expect.poll(() => result.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  mode = 'timeout'
  await page.getByRole('button', { name: 'Abfrage ausführen', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('Zeitlimit')
  closeSocket()
  await expect(page.getByRole('complementary', { name: 'Datenbankkontext' })).toContainText(
    'getrennt',
  )
})
