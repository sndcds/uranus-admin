import { test, expect } from '../fixtures/authenticated'
import {
  mockQueueOperations,
  queueOperations,
  operationDelivery,
  operationNotifications,
  checkOperations,
} from '../fixtures/operations-queues'
import { notification } from '../fixtures/notifications'

const routes = [
  ['partner-requests', '/queues/partner_requests'],
  ['team-invitations', '/queues/team_invitations'],
  ['user-activation', '/queues/user_activation'],
  ['notifications', '/notifications'],
  ['notification-detail', `/notifications/${notification.id}`],
  ['deliveries', '/notifications/deliveries'],
  ['delivery-detail', `/notifications/deliveries/${operationDelivery.id}`],
  ['checks', '/checks'],
] as const
for (const viewport of [
  { width: 1440, height: 1000, name: 'desktop' },
  { width: 1024, height: 768, name: 'tablet' },
  { width: 390, height: 844, name: 'mobile' },
  { width: 360, height: 800, name: 'small-mobile' },
])
  test(`operations review at ${viewport.width}px`, async ({ page }, info) => {
    test.skip(info.project.name !== 'desktop', 'Explicit viewport matrix runs once.')
    test.setTimeout(120000)
    await page.setViewportSize(viewport)
    await mockQueueOperations(page)
    for (const [name, path] of routes) {
      await page.goto(path)
      await expect(
        page.getByRole('region', { name: 'Technische Informationen', exact: true }),
      ).toBeVisible()
      await expect(page.getByText('Daten werden geladen …', { exact: true })).toHaveCount(0)
      await expect(page.getByText('Abruf fehlgeschlagen', { exact: true })).toHaveCount(0)
      if (name === 'notification-detail') {
        await page.getByRole('button', { name: 'Vorschau laden' }).click()
        await expect(page.frameLocator('iframe').locator('h1')).toBeVisible()
        await expect(page.locator('details')).not.toHaveAttribute('open', '')
      }
      if (name === 'delivery-detail')
        await expect(page.getByRole('combobox', { name: 'Zuständig', exact: true })).toBeVisible()
      for (const table of await page.locator('main table').all()) {
        await expect(table.locator('caption')).not.toBeEmpty()
        const display = await table
          .locator('tbody tr')
          .first()
          .evaluate((el) => getComputedStyle(el).display)
        expect(display).toBe(viewport.width > 1100 ? 'table-row' : 'grid')
        if (viewport.width < 640)
          expect(
            await table
              .locator('tbody tr')
              .first()
              .evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(' ').length),
          ).toBe(1)
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      )
      for (const control of await page
        .locator(
          'main button:visible, main select:visible, main input:visible, main .action-link:visible',
        )
        .all()) {
        expect((await control.boundingBox())!.height).toBeGreaterThanOrEqual(44)
      }
      // Preview loading scrolls its trigger into view. Capture the page from its
      // actual top so fixed shell controls are not painted halfway down the image.
      await page.evaluate(() => {
        if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
        window.scrollTo({ top: 0, behavior: 'instant' })
      })
      await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
      await page.screenshot({
        path: info.outputPath(`${name}-${viewport.name}.png`),
        fullPage: true,
      })
    }
  })

test('partner fallback stays technical/copyable and queue refresh keeps only the current selection', async ({
  page,
  context,
}) => {
  await mockQueueOperations(page)
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.goto('/queues/partner_requests')
  const table = page.getByRole('table', { name: 'Vorgänge' })
  await expect(
    table.getByRole('heading', { name: /Zielorganisation nicht verfügbar/ }),
  ).toBeVisible()
  await page.getByRole('button', { name: 'UUID der Zielorganisation kopieren' }).click()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
    queueOperations('partner_requests').items[1]!.to_organization_id,
  )
  let release!: () => void
  const gate = new Promise<void>((done) => {
    release = done
  })
  await page.route('**/api/admin/api/v1/work-queues/partner_requests**', async (route) => {
    await gate
    await route.fulfill({
      status: 503,
      json: { error: { code: 'database_unavailable', message: 'Unavailable' } },
    })
  })
  await page.getByRole('button', { name: 'Aktualisieren', exact: true }).click()
  await expect(page.getByText('Daten werden aktualisiert …', { exact: true }).first()).toBeVisible()
  await expect(table).toBeVisible()
  release()
  await expect(
    page.getByText('Die angezeigten Daten sind veraltet.', { exact: false }),
  ).toBeVisible()
  await page.getByRole('textbox', { name: 'Organisation (UUID)' }).fill('invalid')
  await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
  await expect(table).toHaveCount(0)
  await expect(page.getByText('Keine Vorgänge für diese Auswahl.')).toHaveCount(0)
})

test('notification filters restore URL, pagination preserves applied filters and reset clears them', async ({
  page,
}) => {
  await mockQueueOperations(page)
  await page.route('**/api/admin/api/v1/notifications?**', (route) => {
    const query = new URL(route.request().url()).searchParams
    return route.fulfill({
      json: {
        ...operationNotifications,
        pagination: { page: Number(query.get('page') || 1), page_size: 25, total: 51, pages: 3 },
      },
    })
  })
  await page.goto(
    '/notifications?status=active&notification_type=quality_finding&days=7&page_size=25',
  )
  await expect(page.getByRole('combobox', { name: 'Status', exact: true })).toHaveValue('active')
  await page.getByRole('link', { name: 'Weiter', exact: true }).click()
  await expect(page).toHaveURL(/page=2/)
  await expect(page).toHaveURL(/page_size=25/)
  await page.reload()
  await expect(page.getByRole('combobox', { name: 'Zeitraum', exact: true })).toHaveValue('7')
  await page.getByRole('button', { name: 'Filter zurücksetzen', exact: true }).click()
  await expect(page).toHaveURL('/notifications')
  await page.goBack()
  await expect(page.getByRole('combobox', { name: 'Status', exact: true })).toHaveValue('active')
  await page.goto('/notifications?status=invalid')
  await expect(page.getByRole('alert')).toContainText('prüfe deine Eingaben')
  await expect(page.getByRole('table')).toHaveCount(0)
})

test('delivery workflow separates retry from assignment, returns modal focus and respects an existing successor', async ({
  page,
}) => {
  await mockQueueOperations(page)
  await page.goto(`/notifications/deliveries/${operationDelivery.id}`)
  const trigger = page.getByRole('button', { name: 'Erneut versuchen', exact: true })
  await trigger.focus()
  await trigger.press('Enter')
  const dialog = page.getByRole('dialog', { name: 'Erneut versuchen?' })
  await expect(dialog).toContainText('neuer Versandauftrag')
  await page.keyboard.press('Escape')
  await expect(trigger).toBeFocused()
  await expect(page.getByRole('heading', { name: 'Zuständigkeit', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Vorheriger Versand', exact: true })).toHaveAttribute(
    'href',
    `/notifications/deliveries/${operationDelivery.retry_of_delivery_id}`,
  )
  await page.route(`**/api/admin/api/v1/notification-deliveries/${operationDelivery.id}`, (route) =>
    route.fulfill({
      json: {
        ...operationDelivery,
        retries: [
          { ...operationDelivery, id: '10000000-0000-4000-8000-000000000099', status: 'queued' },
        ],
      },
    }),
  )
  await page.getByRole('button', { name: 'Aktualisieren', exact: true }).click()
  await expect(trigger).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'Weiterer Versuch: Ausstehend' })).toBeVisible()
})

for (const status of [403, 404])
  test(`details clear identity data after ${status}`, async ({ page }) => {
    await mockQueueOperations(page)
    for (const path of [
      `/notifications/${notification.id}`,
      `/notifications/deliveries/${operationDelivery.id}`,
    ]) {
      await page.goto(path)
      await expect(
        page.getByRole('region', { name: 'Technische Informationen', exact: true }),
      ).toBeVisible()
      const api = path.includes('/deliveries/')
        ? `/notification-deliveries/${operationDelivery.id}`
        : path
      await page.route(`**/api/admin/api/v1${api}`, (route) =>
        route.fulfill({
          status,
          json: {
            error: {
              code: status === 403 ? 'permission_denied' : 'record_not_found',
              message: 'Denied',
            },
          },
        }),
      )
      await page.getByRole('button', { name: 'Aktualisieren', exact: true }).click()
      await expect(
        page.getByRole('region', { name: 'Technische Informationen', exact: true }),
      ).toHaveCount(0)
      await expect(page.getByText('recipient@example.test')).toHaveCount(0)
      await expect(page.getByRole('alert')).toBeVisible()
    }
  })

test('check monitor shows pending status, elapsed duration and failure semantics without inventing completion', async ({
  page,
}) => {
  await mockQueueOperations(page)
  await page.goto('/checks')
  await expect(page.getByRole('region', { name: 'Aktueller Lauf', exact: true })).toContainText(
    'Läuft',
  )
  await expect(page.getByRole('button', { name: 'Prüfung läuft …' })).toBeDisabled()
  await expect(page.getByText('Automatische Aktualisierung (UI)')).toBeVisible()
  await expect(page.getByRole('table').getByText('2 min 5 s · inkl. Wartezeit')).toHaveCount(2)
  await expect(page.getByText(/keine automatische Behebung abgeleitet/)).toBeVisible()
  await page.route('**/api/admin/api/v1/check-runs?**', (route) =>
    route.fulfill({ json: { ...checkOperations, items: [] } }),
  )
  await page.getByRole('button', { name: 'Aktualisieren', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Aktueller Lauf', exact: true })).toHaveCount(0)
  await expect(page.getByText('Noch keine gespeicherten Prüfläufe.')).toBeVisible()
})

for (const kind of ['partner_requests', 'team_invitations', 'user_activation'] as const) {
  for (const status of [401, 403])
    test(`${kind} clears protected rows on ${status}`, async ({ page }) => {
      await mockQueueOperations(page)
      await page.goto(`/queues/${kind}`)
      await expect(page.getByRole('table', { name: 'Vorgänge' })).toBeVisible()
      await page.route(`**/api/admin/api/v1/work-queues/${kind}**`, (route) =>
        route.fulfill({
          status,
          json: {
            error: {
              code: status === 401 ? 'authentication_required' : 'permission_denied',
              message: 'Denied',
            },
          },
        }),
      )
      await page.getByRole('button', { name: 'Aktualisieren', exact: true }).click()
      await expect(page.getByRole('table', { name: 'Vorgänge' })).toHaveCount(0)
      if (status === 403) await expect(page.getByRole('alert')).toContainText('Zugriff gesperrt')
      else await expect(page).toHaveURL(/\/login/)
    })
  test(`${kind} preserves filters and page size through pagination`, async ({ page }) => {
    await mockQueueOperations(page)
    await page.route(`**/api/admin/api/v1/work-queues/${kind}**`, (route) => {
      const query = new URL(route.request().url()).searchParams
      return route.fulfill({
        json: {
          ...queueOperations(kind),
          pagination: { page: Number(query.get('page') || 1), page_size: 25, total: 51, pages: 3 },
        },
      })
    })
    await page.goto(`/queues/${kind}?min_age_days=7&page_size=25`)
    await page.getByRole('link', { name: 'Weiter', exact: true }).click()
    await expect(page).toHaveURL(/page=2/)
    await expect(page).toHaveURL(/min_age_days=7/)
    await expect(page).toHaveURL(/page_size=25/)
    await page.goto(`/queues/${kind}?min_age_days=7&min_age_days=8`)
    await expect(page.getByRole('alert')).toContainText('prüfe deine Eingaben')
    await expect(page.getByRole('table')).toHaveCount(0)
  })
}

test('delivery filters keep exact kind, organization, period and status in the URL', async ({
  page,
}) => {
  await mockQueueOperations(page)
  await page.goto(
    '/notifications/deliveries?status=failed&delivery_kind=digest&days=30&organization_id=10000000-0000-4000-8000-000000000010',
  )
  await expect(page.getByRole('combobox', { name: 'Art', exact: true })).toHaveValue('digest')
  await expect(page.getByRole('textbox', { name: 'Organisation (UUID)' })).toHaveValue(
    '10000000-0000-4000-8000-000000000010',
  )
  await page
    .getByRole('combobox', { name: 'Status', exact: true })
    .selectOption('permanent_failure')
  const request = page.waitForRequest(
    (r) =>
      r.url().includes('/notification-deliveries?') && r.url().includes('status=permanent_failure'),
  )
  await page.getByRole('button', { name: 'Filter anwenden' }).click()
  const query = new URL((await request).url()).searchParams
  expect(query.get('delivery_kind')).toBe('digest')
  expect(query.get('days')).toBe('30')
  await expect(page.getByText('Automatischer Versand beendet.')).toBeVisible()
  await page.getByRole('button', { name: 'Filter zurücksetzen', exact: true }).click()
  await expect(page).toHaveURL('/notifications/deliveries')
  await expect(page.getByRole('combobox', { name: 'Status', exact: true })).toHaveValue('')
})

test('long detail identities and stored payload stay contained at 360px', async ({ page }) => {
  await mockQueueOperations(page)
  await page.setViewportSize({ width: 360, height: 800 })
  const longName = 'SehrLangerDatensatzname'.repeat(12)
  await page.route(`**/api/admin/api/v1/notifications/${notification.id}`, (route) =>
    route.fulfill({
      json: {
        ...operationNotifications.items[0],
        entity_name: longName,
        deliveries: [],
        delivery_enabled: false,
        payload: { ...notification.payload, organization_name: longName, entity_name: longName },
      },
    }),
  )
  await page.goto(`/notifications/${notification.id}`)
  await expect(page.getByRole('heading', { name: longName, exact: true })).toBeVisible()
  await page.getByText('Gespeicherte Daten', { exact: true }).click()
  await expect(page.locator('details pre')).toContainText(longName)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.route(`**/api/admin/api/v1/notification-deliveries/${operationDelivery.id}`, (route) =>
    route.fulfill({
      json: {
        ...operationDelivery,
        subject: longName,
        recipient: `${'recipient'.repeat(30)}@example.test`,
      },
    }),
  )
  await page.goto(`/notifications/deliveries/${operationDelivery.id}`)
  await expect(page.getByRole('heading', { name: longName, exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
