import { test, expect, type Page } from '@playwright/test'
import { detailFixture } from '../fixtures/entities'
import { graphFixture, graphPath } from '../fixtures/graph'

async function login(page: Page, username = 'operator') {
  await page.getByLabel('Benutzername', { exact: true }).fill(username)
  await page.getByLabel('Passwort', { exact: true }).fill('test-only-password')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
}
async function noShell(page: Page) {
  await expect(page.locator('aside')).toHaveCount(0)
  await expect(page.locator('header')).toHaveCount(0)
  await expect(page.locator('#main-content')).toHaveCount(0)
  await expect(page.getByRole('navigation', { name: 'Hauptnavigation' })).toHaveCount(0)
}

for (const target of [
  '/',
  '/events/20000000-0000-4000-8000-000000000001',
  graphPath,
  '/#open-queues',
]) {
  test(`anonymous SSR and client never render protected content: ${target}`, async ({
    page,
    request,
  }, testInfo) => {
    const response = await request.get(target.split('#')[0]!, { maxRedirects: 0 })
    expect(response.status()).toBe(302)
    expect(response.headers().location).toContain('/login?redirect=')
    expect(await response.text()).not.toMatch(/Hauptnavigation|main-content|Test-Hafenbühne/)
    const requests: string[] = []
    page.on('request', (r) => {
      if (r.url().includes('/api/admin/api/')) requests.push(r.url())
    })
    await page.addInitScript(() => {
      const state = window as typeof window & { protectedFlash: boolean }
      state.protectedFlash = false
      new MutationObserver(() => {
        if (document.querySelector('aside, header, #main-content')) state.protectedFlash = true
      }).observe(document, { childList: true, subtree: true })
    })
    await page.goto(target)
    await expect(page.getByRole('heading', { name: 'Anmeldung', exact: true })).toBeVisible()
    await noShell(page)
    expect(
      await page.evaluate(
        () => (window as typeof window & { protectedFlash: boolean }).protectedFlash,
      ),
    ).toBe(false)
    expect(requests).toEqual([])
    const url = new URL(page.url())
    expect(url.pathname).toBe('/login')
    expect(url.searchParams.get('redirect')! + url.hash).toBe(target)
    await page.screenshot({
      path: testInfo.outputPath(target === '/' ? 'login.png' : 'anonymous-deep-link.png'),
      fullPage: true,
    })
  })
}

test('login, reload, authenticated login redirect, logout and browser Back', async ({
  page,
  context,
}, testInfo) => {
  const errors: string[] = []
  page.on('console', (message) => {
    if (/hydration/i.test(message.text())) errors.push(message.text())
  })
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/')
  await login(page)
  await expect(page).toHaveURL('http://127.0.0.1:3100/')
  await expect(page.getByText('Test-Hafenbühne')).toBeVisible()
  await expect(page.locator('#main-content')).toBeVisible()
  await page.screenshot({
    path: testInfo.outputPath('authenticated-dashboard.png'),
    fullPage: true,
  })
  const cookie = (await context.cookies()).find((item) => item.name.endsWith('admin_session'))!
  expect(cookie.httpOnly).toBe(true)
  expect(cookie.sameSite).toBe('Strict')
  if (process.env.TEST_PRODUCTION === '1') expect(cookie.secure).toBe(true)
  expect(await page.evaluate(() => document.cookie)).not.toContain(cookie.value)
  expect(await page.content()).not.toContain(cookie.value)
  expect(await page.content()).not.toContain('test-only-password')
  expect(await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]))).not.toContain(
    cookie.value,
  )
  // APIRequestContext does not apply Chromium's secure-loopback exception.
  const ssr = await context.request.get('/', {
    headers: { Cookie: `${cookie.name}=${cookie.value}` },
  })
  expect(await ssr.text()).toContain('main-content')
  expect(
    await page.evaluate(
      (html) => {
        const document = new DOMParser().parseFromString(html, 'text/html')
        return [...document.querySelectorAll('button')].find(
          (button) => button.textContent?.trim() === 'Abmelden',
        )?.disabled
      },
      await ssr.text(),
    ),
  ).toBe(true)
  expect(await ssr.text()).not.toContain(cookie.value)
  await page.reload()
  await expect(page.getByRole('button', { name: 'Abmelden', exact: true })).toBeVisible()
  await page.goto('/login')
  await expect(page).toHaveURL('http://127.0.0.1:3100/')
  await page.goto('/findings')
  await page.getByRole('button', { name: 'Abmelden', exact: true }).click()
  await expect(page).toHaveURL('http://127.0.0.1:3100/login')
  await noShell(page)
  expect(
    (await context.cookies()).filter((item) => item.name.endsWith('admin_session')),
  ).toHaveLength(0)
  await page.goBack()
  await expect(page).toHaveURL(/\/login(?:\?|$)/)
  await noShell(page)
  await page.goto('/events/20000000-0000-4000-8000-000000000001')
  await expect(page).toHaveURL(/\/login\?redirect=/)
  await noShell(page)
  expect(errors).toEqual([])
})

test('restores event detail after login', async ({ page }) => {
  const detail = detailFixture('events')
  const target = `/events/${detail.item.entity_key}`
  await page.route('**/api/admin/api/v1/events/*', (route) => route.fulfill({ json: detail }))
  await page.goto(target)
  await login(page)
  await expect(page).toHaveURL(`http://127.0.0.1:3100${target}`)
  await expect(
    page.getByRole('heading', { name: 'Fixture events', exact: true, level: 2 }),
  ).toBeVisible()
})
test('restores full graph query and inherited fragment', async ({ page }) => {
  await page.route('**/api/admin/api/v1/graph?**', (route) => route.fulfill({ json: graphFixture }))
  await page.goto(`${graphPath}#details`)
  await login(page)
  await expect(page).toHaveURL(`http://127.0.0.1:3100${graphPath}#details`)
  await expect(page.locator('.graph-node')).toHaveCount(12)
})
test('invalid credentials stay on login; external redirect is rejected', async ({ page }) => {
  await page.goto('/login?redirect=https://evil.example')
  await login(page, 'missing')
  await expect(page.getByRole('alert')).toHaveText('Anmeldung fehlgeschlagen.')
  await noShell(page)
  await login(page)
  await expect(page).toHaveURL('http://127.0.0.1:3100/')
})
test('ordinary accounts cannot enter the shell, including after reload', async ({ page }) => {
  await page.goto('/login')
  await login(page, 'ordinary')
  await expect(page.getByRole('heading', { name: 'Zugriff gesperrt' })).toBeVisible()
  await noShell(page)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Zugriff gesperrt' })).toBeVisible()
  await noShell(page)
  await page.getByRole('button', { name: 'Abmelden', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Anmeldung', exact: true })).toBeVisible()
})
test('expired session redirects from a deep route and clears the shell', async ({
  page,
  context,
}) => {
  await page.goto('/login')
  await login(page)
  await expect(page.getByText('Test-Hafenbühne')).toBeVisible()
  await page.goto('/findings?severity=warning')
  await expect(page.getByText('Test-Hafenbühne')).toBeVisible()
  const cookie = (await context.cookies()).find((item) => item.name.endsWith('admin_session'))!
  await context.addCookies([{ ...cookie, value: 'X'.repeat(43) }])
  await page.getByRole('button', { name: 'Anwenden', exact: true }).click()
  await expect(page).toHaveURL(/\/login\?redirect=/)
  expect(new URL(page.url()).searchParams.get('redirect')).toContain('/findings?')
  await noShell(page)
  await login(page)
  await expect(page).toHaveURL(/\/findings\?/)
  await expect(page.getByText('Test-Hafenbühne')).toBeVisible()
})
test('protected 403 shows access denied without logout or login redirect', async ({ page }) => {
  await page.goto('/login')
  await login(page)
  await expect(page.getByText('Test-Hafenbühne')).toBeVisible()
  await page.route('**/api/admin/api/v1/**', (route) =>
    route.fulfill({
      status: 403,
      json: { error: { code: 'admin_access_denied', message: 'denied' } },
    }),
  )
  await page.getByLabel('Zeitraum', { exact: true }).selectOption('today')
  await expect(page.getByText('Zugriff gesperrt').first()).toBeVisible()
  await expect(page).toHaveURL('http://127.0.0.1:3100/')
  await expect(page.getByRole('button', { name: 'Abmelden', exact: true })).toBeVisible()
})
test('failed server logout clears the shell and reports failed revocation', async ({ page }) => {
  await page.goto('/login')
  await login(page)
  await expect(page.getByText('Test-Hafenbühne')).toBeVisible()
  await page.route('**/api/admin/auth/logout', (route) => route.fulfill({ status: 503, json: {} }))
  await page.getByRole('button', { name: 'Abmelden', exact: true }).click()
  await expect(page).toHaveURL('http://127.0.0.1:3100/login')
  await noShell(page)
  await expect(page.getByRole('alert')).toContainText('Serversitzung konnte nicht beendet werden')
})

test('login works under the existing production CSP', async ({ page }) => {
  test.skip(process.env.TEST_PRODUCTION !== '1', 'Requires the production client build')
  const policy =
    "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'"
  await page.addInitScript(() => {
    const state = window as typeof window & { violations: string[] }
    state.violations = []
    document.addEventListener('securitypolicyviolation', (event) =>
      state.violations.push(event.effectiveDirective),
    )
  })
  await page.route('**/*', async (route) => {
    if (route.request().resourceType() !== 'document') return route.continue()
    const response = await route.fetch()
    await route.fulfill({
      response,
      headers: { ...response.headers(), 'content-security-policy': policy },
    })
  })
  await page.goto('/login')
  await login(page)
  await expect(page.getByText('Test-Hafenbühne')).toBeVisible()
  expect(
    await page.evaluate(() => (window as typeof window & { violations: string[] }).violations),
  ).toEqual([])
})
