import { test, expect } from '../fixtures/authenticated'
import { statisticsFixture } from '../fixtures/statistics'
import { eventContentFixture } from '../fixtures/event-content'
import { summary } from '../fixtures/api'
import { qualityRules } from '../../app/utils/quality'

const counts = {
  ...Object.fromEntries(Object.keys(qualityRules).map((rule) => [rule, 0])),
  venue_missing_logo: 12,
  organization_missing_logo: 4,
  logo_unsupported_format: 7,
  postal_code_whitespace: 2,
  venue_missing_geolocation: 1,
  event_date_end_before_start: 1,
}
const qualityFixture = {
  ...summary,
  quality: {
    total: 27,
    errors: 1,
    warnings: 19,
    info: 7,
    mode: 'persisted',
    rules: Object.keys(counts),
    rule_counts: counts,
  },
}
const sizes = [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'tablet', width: 1024, height: 768 },
  { name: 'mobile', width: 390, height: 844 },
  { name: 'small', width: 360, height: 800 },
]
test.beforeEach(async ({ page }) => {
  await page.route('**/api/admin/api/v1/statistics/**', (route) => {
    const url = new URL(route.request().url())
    return route.fulfill({
      json: url.pathname.endsWith('/events/content')
        ? eventContentFixture(url.searchParams)
        : statisticsFixture(url.searchParams),
    })
  })
  await page.route('**/api/admin/api/v1/dashboard/summary*', (route) => {
    expect(new URL(route.request().url()).searchParams.has('geo_scope_id')).toBe(false)
    return route.fulfill({ json: qualityFixture })
  })
})

for (const size of sizes) {
  test(`creation analytics ${size.width}`, async ({ page }, info) => {
    test.skip(info.project.name !== 'desktop', 'Explicit four-viewport matrix runs once')
    await page.setViewportSize(size)
    await page.goto('/statistics?period=7d')
    const chart = page.getByRole('img', { name: 'Neue Entitäten im Zeitverlauf' })
    await expect(page.locator('.statistics-metric')).toHaveCount(7)
    await expect(
      page
        .getByRole('navigation', { name: 'Statistikbereich' })
        .getByRole('button', { name: 'Erstellung' }),
    ).toHaveAttribute('aria-pressed', 'true')
    await chart.focus()
    for (const key of ['Home', 'ArrowRight', 'End', 'ArrowLeft']) {
      await page.keyboard.press(key)
      await expect(page.locator('.statistics-tooltip')).toContainText('Veranstaltungen')
    }
    await page.keyboard.press('Escape')
    await expect(page.locator('.statistics-tooltip')).toHaveCount(0)
    const toggle = page
      .locator('.statistics-legend')
      .getByRole('button', { name: 'Benutzer', exact: true })
    await toggle.focus()
    await page.keyboard.press('Enter')
    await expect(toggle).toHaveAttribute('aria-pressed', 'false')
    await expect(page.locator('.statistics-series')).toHaveCount(6)
    await page.keyboard.press('Enter')
    await expect(page.locator('.statistics-series')).toHaveCount(7)
    const recent = page.getByRole('table', { name: 'Zuletzt angelegte Entitäten' })
    await expect(recent.getByRole('link', { name: /^Öffnen:/ })).toHaveCount(7)
    await expect(recent.getByRole('link', { name: 'Öffnen: Jazz im Hof 2027' })).toHaveAttribute(
      'href',
      '/events/20000000-0000-4000-8000-000000000003',
    )
    const footer = page.getByRole('region', { name: 'Technische Informationen' })
    await expect(footer).toContainText('Europe/Berlin')
    await expect(footer.locator('time')).toHaveCount(3)
    await expect(footer).toContainText('Vergleich aktivNein')
    await page.getByText(/Daten als Tabelle/).click()
    const tableScroll = page.getByRole('region', { name: /Anzahl pro Zeitintervall/ })
    await expect(tableScroll).toHaveAttribute('tabindex', '0')
    await expect(tableScroll.getByRole('table')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.getByText(/Daten als Tabelle/).click()
    await page.getByRole('heading', { name: 'Neue Entitäten', exact: true }).click()
    await page.screenshot({ path: info.outputPath(`statistics-${size.name}.png`), fullPage: true })
    if (size.name === 'desktop') {
      await page.getByRole('switch').check()
      await expect(footer).toContainText('Vergleich aktivJa')
      await page.screenshot({
        path: info.outputPath('statistics-compare-desktop.png'),
        fullPage: true,
      })
      await page.getByRole('button', { name: 'Benutzerdefiniert' }).click()
      await page.getByLabel('Von', { exact: true }).fill('2026-09-14')
      await page.getByLabel('Bis einschließlich').fill('2026-09-16')
      await page.screenshot({
        path: info.outputPath('statistics-custom-desktop.png'),
        fullPage: true,
      })
      for (const [from, to] of [
        ['2026-09-16', '2026-09-14'],
        ['2024-01-01', '2026-09-14'],
      ]) {
        await page.getByLabel('Von', { exact: true }).fill(from!)
        await page.getByLabel('Bis einschließlich').fill(to!)
        await page.getByRole('button', { name: 'Zeitraum anwenden' }).click()
        await expect(page.getByRole('alert')).toContainText('höchstens 365 Tagen')
        await expect(page).not.toHaveURL(/period=custom/)
      }
    }
    for (const control of await page
      .locator(
        '.statistics-period-bar button, .statistics-legend button, .analytics-view-nav button',
      )
      .all())
      expect((await control.boundingBox())!.height).toBeGreaterThanOrEqual(44)
  })

  test(`event content analytics ${size.width}`, async ({ page }, info) => {
    test.skip(info.project.name !== 'desktop', 'Explicit four-viewport matrix runs once')
    await page.setViewportSize(size)
    await page.goto('/statistics?view=event-content&period=30d&status=released&compare=previous')
    await expect(page.getByRole('region', { name: 'Kategorie vorhanden' })).toContainText(
      '8 von 8 Events',
    )
    await expect(page.getByRole('region', { name: 'Genre vorhanden' })).toContainText(
      '2 Events ohne Genre',
    )
    await expect(page.getByText(/Erstellt, nicht Veranstaltungsdatum/)).toBeVisible()
    await expect(page.getByText('Vergleich: gleichlange Vorperiode.')).toBeVisible()
    await expect(page.getByRole('region', { name: 'Technische Informationen' })).toContainText(
      'Vergleich von',
    )
    for (const title of ['Top 10 Kategorien', 'Top 10 Genres', 'Top 10 Event-Typen'])
      await expect(page.getByRole('region', { name: title, exact: true })).toContainText('Rang ↑ 2')
    await page.screenshot({
      path: info.outputPath(`event-content-${size.name}.png`),
      fullPage: true,
    })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.getByRole('combobox', { name: 'Zeitraum', exact: true }).selectOption('all')
    await expect(page.getByRole('switch')).toBeDisabled()
    await expect(page.getByRole('region', { name: 'Technische Informationen' })).not.toContainText(
      'Vergleich von',
    )
    await expect(
      page.getByRole('region', { name: 'Technische Informationen' }).locator('time'),
    ).toHaveCount(1)
  })

  test(`quality workspace ${size.width}`, async ({ page }, info) => {
    test.skip(info.project.name !== 'desktop', 'Explicit four-viewport matrix runs once')
    await page.setViewportSize(size)
    await page.goto('/quality')
    await expect(page.getByText(/Persistierter Bestand · Systemweit/)).toBeVisible()
    await expect(page.getByRole('link', { name: 'Prüfläufe', exact: true }).last()).toHaveAttribute(
      'href',
      '/checks',
    )
    const status = page.getByRole('region', { name: 'Qualitätsstatus' })
    await expect(status).toContainText('Fehler1')
    await expect(status).toContainText('Warnungen19')
    await expect(status).toContainText('Hinweise7')
    await expect(status).toContainText('Befunde27')
    const postal = page.locator('[data-quality-rule=postal_code_whitespace]')
    await expect(postal).toContainText('Warnung')
    const postalHref = await postal.getByRole('link').getAttribute('href')
    expect(new URL(postalHref!, 'http://fixture').searchParams.has('entity_type')).toBe(false)
    await expect(
      page.locator('[data-quality-rule=venue_missing_geolocation]').getByRole('link'),
    ).toHaveAttribute(
      'href',
      '/findings?rule=venue_missing_geolocation&entity_type=venue&status=open',
    )
    await expect(page.getByRole('region', { name: 'Technische Informationen' })).toContainText(
      'Persistiert',
    )
    await expect(
      page.getByRole('region', { name: 'Technische Informationen' }).locator('time'),
    ).toHaveCount(0)
    await page.screenshot({ path: info.outputPath(`quality-${size.name}.png`), fullPage: true })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    for (const link of await page.locator('.quality-rule-groups a').all())
      expect((await link.boundingBox())!.height).toBeGreaterThanOrEqual(44)
  })
}

test('all creation presets stay supported and quality preserves stale, zero and unavailable counts', async ({
  page,
}) => {
  await page.goto('/statistics')
  for (const [period, label] of [
    ['24h', 'Letzte 24 Stunden'],
    ['7d', 'Letzte 7 Tage'],
    ['30d', 'Letzte 30 Tage'],
    ['90d', 'Letzte 90 Tage'],
  ]) {
    await page.getByRole('button', { name: label!, exact: true }).click()
    await expect(page.getByRole('button', { name: label!, exact: true })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await expect(page.locator('.statistics-metric')).toHaveCount(7)
    expect(new URL(page.url()).searchParams.get('period')).toBe(period)
  }
  await page.goto('/quality')
  await expect(page.locator('[data-quality-rule=venue_missing_logo]')).toContainText('12')
  await page.route('**/api/admin/api/v1/dashboard/summary*', (route) =>
    route.fulfill({
      status: 503,
      json: { error: { code: 'database_unavailable', message: 'Unavailable' } },
    }),
  )
  await page.getByRole('button', { name: 'Aktualisieren', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('veraltet')
  await expect(page.locator('[data-quality-rule=venue_missing_logo]')).toContainText('12')
  await page.route('**/api/admin/api/v1/dashboard/summary*', (route) =>
    route.fulfill({
      json: {
        ...qualityFixture,
        quality: {
          ...qualityFixture.quality,
          total: 0,
          errors: 0,
          warnings: 0,
          info: 0,
          rule_counts: { venue_missing_logo: 0 },
        },
      },
    }),
  )
  await page.getByRole('button', { name: 'Erneut versuchen' }).click()
  await expect(page.locator('[data-quality-rule=venue_missing_logo]')).toContainText('0')
  await expect(page.locator('[data-quality-rule=organization_missing_logo]')).toContainText(
    'Nicht verfügbar',
  )
  await expect(page.getByText('Keine aktuellen Qualitätsbefunde.')).toBeVisible()
})
