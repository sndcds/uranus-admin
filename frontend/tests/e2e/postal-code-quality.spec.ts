import { test, expect } from '../fixtures/authenticated'
import { summary, findings } from '../fixtures/api'

const rule = 'postal_code_whitespace'
const message = 'Postleitzahl enthält führende oder abschließende Leerzeichen.'
const owners = [
  { kind: 'organization', section: 'organizations', label: 'Organisation' },
  { kind: 'venue', section: 'venues', label: 'Ort' },
] as const

for (const mode of ['live', 'persisted'] as const) {
  test(`postal code quality drilldown for both owners: ${mode}`, async ({ page }) => {
    const key = findings.items[0]!.entity_key
    let receivedFilters: URLSearchParams | undefined
    await page.route('**/api/admin/api/v1/**', async (route) => {
      const url = new URL(route.request().url())
      if (url.pathname.endsWith('/summary'))
        return route.fulfill({
          json: {
            ...summary,
            quality: {
              total: 2,
              errors: 0,
              warnings: 2,
              info: 0,
              rules: [rule],
              rule_counts: { [rule]: 2 },
              mode,
            },
          },
        })
      if (url.pathname.endsWith('/findings')) {
        receivedFilters = url.searchParams
        return route.fulfill({
          json: {
            ...findings,
            mode,
            items: owners.map((owner) => ({
              ...findings.items[0],
              id: `${rule}:${owner.kind}:${key}:postal_code`,
              rule,
              field: 'postal_code',
              severity: 'warning',
              entity_type: owner.kind,
              entity_name: `PLZ-Test ${owner.label}`,
              message,
              address: {},
              metadata: { reason: 'leading_or_trailing_whitespace' },
              action: {
                type: 'view',
                route: 'activity',
                entity_type: owner.kind,
                entity_key: key,
                href: `/${owner.section}/${key}`,
              },
            })),
            pagination: { page: 1, page_size: 50, total: 2, pages: 1 },
          },
        })
      }
      return route.fulfill({ json: {} })
    })
    await page.goto('/quality')
    await expect(page.getByRole('heading', { name: 'Adressqualität' })).toBeVisible()
    const link = page.getByRole('link', { name: /Postleitzahlen mit Leerzeichen/ })
    await expect(link).toContainText('2')
    await expect(link).toContainText('Warnung')
    await expect(link).toContainText('Schlechte Datenqualität')
    await link.click()
    await expect(page).toHaveURL(new RegExp(`/findings\\?rule=${rule}`))
    const rows = page.getByRole('list', { name: 'Befunde', exact: true }).getByRole('listitem')
    await expect(rows).toHaveCount(2)
    for (const owner of owners) {
      const row = rows.filter({ hasText: `PLZ-Test ${owner.label}` })
      await expect(row.getByText(owner.label, { exact: true })).toBeVisible()
      await expect(row.getByText('Warnung', { exact: true })).toBeVisible()
      await expect(row).toContainText('Feld: postal_code')
      await expect(row).toContainText(message)
      await expect(row.getByRole('link', { name: 'Im Admin ansehen' })).toHaveAttribute(
        'href',
        `/${owner.section}/${key}`,
      )
    }
    await rows
      .first()
      .getByRole('button', { name: 'Befund zu PLZ-Test Organisation ansehen' })
      .click()
    await expect(page.getByRole('dialog', { name: 'PLZ-Test Organisation' })).toContainText(
      `${rule} / postal_code`,
    )
    expect(receivedFilters?.get('rule')).toBe(rule)
    expect(receivedFilters?.get('entity_type')).toBeNull()
    expect(receivedFilters?.get('mode')).toBe(mode)
  })
}
