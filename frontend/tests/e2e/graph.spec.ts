import { test, expect, expectLogoutAvailable } from '../fixtures/authenticated'
import { graphFixture, graphPath } from '../fixtures/graph'

test.beforeEach(async ({ page }) => {
  await page.route('**/api/admin/auth/session', (route) =>
    route.fulfill({ json: { subject: 'admin:test-only-operator', system_admin: true } }),
  )
  await page.route('**/api/admin/api/v1/graph**', (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/search'))
      return route.fulfill({ json: { items: [graphFixture.nodes[0]] } })
    const type = url.searchParams.get('root_type') ?? 'organization'
    const key = url.searchParams.get('root_key') ?? graphFixture.root.key
    return route.fulfill({ json: { ...graphFixture, root: { type, key } } })
  })
})

test('search, explore, select, filter and navigate back', async ({ page }, info) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/graph')
  await expectLogoutAvailable(page)
  await expect(page.getByRole('heading', { name: 'Zusammenhänge entdecken' })).toBeVisible()
  await page.getByLabel('Nach Name oder UUID suchen', { exact: true }).fill('Rendsburg')
  await page
    .getByRole('button', { name: 'Kulturzentrum Rendsburg e.V. Organisation', exact: true })
    .click()
  await expect(page.locator('.graph-node')).toHaveCount(12)
  await expect(page.getByRole('heading', { name: 'Kulturzentrum Rendsburg e.V.' })).toBeVisible()
  const node = page.locator('.graph-node').filter({ hasText: 'Max Mustermann' })
  await node.focus()
  await page.keyboard.press('Enter')
  const panel = page.getByRole('complementary', { name: 'Knotendetails' })
  await expect(panel.getByRole('heading', { name: 'Max Mustermann' })).toBeVisible()
  await panel.getByRole('button', { name: /Kulturzentrum Rendsburg e.V./ }).click()
  await expect(panel.getByRole('heading', { name: 'Kulturzentrum Rendsburg e.V.' })).toBeVisible()
  await page.getByRole('button', { name: 'Vergrößern', exact: true }).click()
  await page.getByRole('button', { name: 'Ansicht einpassen', exact: true }).click()
  await page.getByLabel('Entitätstypen', { exact: true }).selectOption('venue')
  await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
  await expect(page.locator('.graph-node')).toHaveCount(3)
  await page.goBack()
  await expect(page.locator('.graph-node')).toHaveCount(12)
  expect(errors).toEqual([])
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  await page.screenshot({ path: info.outputPath('relationship-graph.png'), fullPage: true })
})

test('user search accepts canonical detail links and opens the graph', async ({ page }) => {
  const user = graphFixture.nodes[1]!
  await page.route('**/api/admin/api/v1/graph/search?**', (route) =>
    route.fulfill({ json: { items: [user] } }),
  )
  await page.goto('/graph')
  await expectLogoutAvailable(page)
  await page.getByLabel('Nach Name oder UUID suchen', { exact: true }).fill('Max')
  await page.getByRole('button', { name: 'Max Mustermann Benutzer', exact: true }).click()
  await expect(page).toHaveURL(/root_type=user/)
  await expect(page.locator('.graph-node')).toHaveCount(12)
  const panel = page.getByRole('complementary', { name: 'Knotendetails' })
  await expect(panel.getByRole('heading', { name: user.label })).toBeVisible()
  await expect(panel.getByRole('link', { name: 'Im Admin ansehen', exact: true })).toHaveAttribute(
    'href',
    `/users/${user.key}`,
  )
  await expect(page.getByText(/Suche fehlgeschlagen:/)).toHaveCount(0)
})

test('deep link and selected node as new root', async ({ page }) => {
  await page.goto(graphPath)
  await expect(page.locator('.graph-node')).toHaveCount(12)
  await page.locator('.graph-node').filter({ hasText: 'Max Mustermann' }).click()
  await page.getByRole('button', { name: 'Als Ausgangspunkt verwenden', exact: true }).click()
  await expect(page).toHaveURL(/root_type=user/)
  await expect(
    page
      .getByRole('complementary', { name: 'Knotendetails' })
      .getByRole('heading', { name: 'Max Mustermann' }),
  ).toBeVisible()
})

test('truncation, failure and empty results are explicit', async ({ page }) => {
  await page.route('**/api/admin/api/v1/graph?**', (route) =>
    route.fulfill({ json: { ...graphFixture, truncated: true } }),
  )
  await page.goto(graphPath)
  await expect(page.getByText(/Darstellung begrenzt:/)).toBeVisible()
  await page.route('**/api/admin/api/v1/graph/search?**', (route) =>
    route.fulfill({ json: { items: [] } }),
  )
  await page.getByLabel('Nach Name oder UUID suchen', { exact: true }).fill('missing')
  await expect(page.getByText('Keine passenden Datensätze gefunden.')).toBeVisible()
  await page.route('**/api/admin/api/v1/graph?**', (route) =>
    route.fulfill({
      status: 503,
      json: { error: { code: 'database_unavailable', message: 'Unavailable' } },
    }),
  )
  await page.reload()
  await expect(page.getByRole('alert')).toContainText('Abruf fehlgeschlagen')
  await expect(page.locator('.graph-node')).toHaveCount(0)
})

test('email-only user labels survive root, neighbor, search and technical details', async ({
  page,
}) => {
  // Backend contract fixture: display_name/username absent, email is the canonical label.
  const user = { ...graphFixture.nodes[1]!, label: 'no-name@example.org' }
  await page.route('**/api/admin/api/v1/graph**', (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/search')) return route.fulfill({ json: { items: [user] } })
    return route.fulfill({
      json: {
        ...graphFixture,
        root: { type: url.searchParams.get('root_type'), key: url.searchParams.get('root_key') },
        nodes: graphFixture.nodes.map((node) => (node.id === user.id ? user : node)),
      },
    })
  })
  await page.goto(`/graph?root_type=user&root_key=${user.key}&depth=2`)
  const node = page.locator('.graph-node').filter({ hasText: user.label })
  const panel = page.getByRole('complementary', { name: 'Knotendetails' })
  await expect(node).toBeVisible()
  await expect(node.locator('text')).toHaveText(user.label)
  await expect(panel.getByRole('heading', { name: user.label, exact: true })).toBeVisible()
  await expect(panel.getByText(user.key, { exact: true })).toBeVisible()
  await expect(panel.getByRole('button', { name: 'UUID kopieren' })).toBeVisible()
  await expect(page.locator('.graph-node').filter({ hasText: user.key })).toHaveCount(0)

  await page.goto(graphPath)
  await expect(node).toBeVisible()
  await node.click()
  await expect(panel.getByRole('heading', { name: user.label, exact: true })).toBeVisible()
  await page.getByLabel('Nach Name oder UUID suchen', { exact: true }).fill(user.label)
  await page.getByRole('button', { name: `${user.label} Benutzer`, exact: true }).click()
  await expect(page).toHaveURL(/root_type=user/)
  await expect(panel.getByRole('heading', { name: user.label, exact: true })).toBeVisible()
})
