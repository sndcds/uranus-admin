import { test, expect } from '../fixtures/authenticated'
import { summary, findings } from '../fixtures/api'

const cases = [
  {
    rule: 'venue_missing_logo',
    label: 'Orte ohne Logo',
    entity: 'venue',
    section: 'venues',
    severity: 'warning',
    count: 12,
  },
  {
    rule: 'organization_missing_logo',
    label: 'Organisationen ohne Logo',
    entity: 'organization',
    section: 'organizations',
    severity: 'warning',
    count: 4,
  },
  {
    rule: 'logo_unsupported_format',
    label: 'Logos in anderem Format',
    entity: 'venue',
    section: 'venues',
    severity: 'info',
    count: 7,
  },
] as const

for (const entry of cases) {
  test(`logo quality drilldown: ${entry.rule}`, async ({ page }, testInfo) => {
    const entityKey = findings.items[0]!.entity_key
    const field = entry.rule === 'logo_unsupported_format' ? 'main_logo.mime_type' : 'main_logo'
    let receivedFilters: URLSearchParams | undefined
    await page.route('**/api/admin/api/v1/**', async (route) => {
      const url = new URL(route.request().url())
      if (url.pathname.endsWith('/summary'))
        return route.fulfill({
          json: {
            ...summary,
            quality: {
              ...summary.quality,
              total: 23,
              warnings: 16,
              info: 7,
              rules: cases.map((item) => item.rule),
              rule_counts: Object.fromEntries(cases.map((item) => [item.rule, item.count])),
            },
          },
        })
      if (url.pathname.endsWith('/findings')) {
        receivedFilters = url.searchParams
        return route.fulfill({
          json: {
            ...findings,
            items: [
              {
                ...findings.items[0],
                id: `${entry.rule}:${entry.entity}:${entityKey}:${field}`,
                field,
                rule: entry.rule,
                entity_type: entry.entity,
                severity: entry.severity,
                entity_name: 'Logo-Testdatensatz',
                message:
                  entry.severity === 'info'
                    ? 'Logo verwendet kein PNG- oder WebP-Format.'
                    : 'Hauptlogo fehlt.',
                action: {
                  type: 'view',
                  route: 'activity',
                  entity_type: entry.entity,
                  entity_key: entityKey,
                  href: `/${entry.section}/${entityKey}`,
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
    await expect(page.getByRole('heading', { name: 'Logos & Bilder' })).toBeVisible()
    for (const item of cases) {
      const link = page.getByRole('link', { name: new RegExp(item.label) })
      await expect(link).toContainText(String(item.count))
      await expect(link).toContainText(
        item.severity === 'info' ? 'Hinweis' : 'Schlechte Datenqualität',
      )
    }
    if (entry.rule === 'venue_missing_logo')
      await page.screenshot({ path: testInfo.outputPath('logo-quality.png'), fullPage: true })
    await page.getByRole('link', { name: new RegExp(entry.label) }).click()
    await expect(page).toHaveURL(
      (url) =>
        url.pathname === '/findings' &&
        url.searchParams.get('rule') === entry.rule &&
        url.searchParams.get('active_only') === 'true',
    )
    const row = page.getByRole('list', { name: 'Befunde', exact: true }).getByRole('listitem')
    await expect(row).toContainText('Logo-Testdatensatz')
    await expect(
      row.getByText(entry.entity === 'venue' ? 'Ort' : 'Organisation', { exact: true }),
    ).toBeVisible()
    await expect(
      row.getByText(entry.severity === 'info' ? 'Hinweis' : 'Warnung', { exact: true }),
    ).toBeVisible()
    await expect(row.getByRole('link', { name: 'Im Admin ansehen' })).toHaveAttribute(
      'href',
      `/${entry.section}/${entityKey}`,
    )
    await row.getByRole('button', { name: 'Befund zu Logo-Testdatensatz ansehen' }).click()
    await expect(page.getByRole('dialog', { name: 'Logo-Testdatensatz' })).toContainText(
      `${entry.rule} / ${field}`,
    )
    expect(receivedFilters?.get('rule')).toBe(entry.rule)
    expect(receivedFilters?.get('entity_type')).toBe(
      entry.rule === 'logo_unsupported_format' ? null : entry.entity,
    )
  })
}

test('quality loading, error retry and empty logo counts', async ({ page }) => {
  let release!: () => void
  const pending = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route('**/api/admin/api/v1/dashboard/summary*', async (route) => {
    await pending
    return route.fulfill({
      status: 503,
      json: { error: { code: 'unavailable', message: 'unavailable' } },
    })
  })
  await page.goto('/quality')
  await expect(page.getByText('Daten werden geladen …')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Logos & Bilder' })).toHaveCount(0)
  release()
  await expect(page.getByText('Abruf fehlgeschlagen')).toBeVisible()
  await page.unroute('**/api/admin/api/v1/dashboard/summary*')
  await page.route('**/api/admin/api/v1/dashboard/summary*', (route) =>
    route.fulfill({
      json: {
        ...summary,
        quality: {
          ...summary.quality,
          total: 0,
          warnings: 0,
          rule_counts: Object.fromEntries(cases.map((item) => [item.rule, 0])),
        },
      },
    }),
  )
  await page.getByRole('button', { name: 'Erneut versuchen' }).click()
  await expect(page.getByText('Keine aktuellen Qualitätsbefunde.')).toBeVisible()
  for (const entry of cases)
    await expect(page.getByRole('link', { name: new RegExp(entry.label) })).toContainText('0')
})
