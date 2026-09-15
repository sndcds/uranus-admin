import { test, expect } from '@playwright/test'

test('production login traverses Nitro, keeps the cookie HttpOnly and removes data on logout', async ({
  page,
  context,
}) => {
  const messages: string[] = []
  page.on('console', (message) => messages.push(message.text()))
  await page.goto('/')
  await expect(page.getByText('Zugang erforderlich').first()).toBeVisible()
  await page.getByLabel('Benutzername', { exact: true }).fill('operator')
  await page.getByLabel('Passwort', { exact: true }).fill('test-only-password')
  const responsePromise = page.waitForResponse('**/api/admin/auth/login')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  const response = await responsePromise
  expect(response.status()).toBe(200)
  const body = await response.json()
  expect(Object.keys(body).sort()).toEqual(['subject', 'system_admin'])
  await expect(page.getByText('Test-Hafenbühne')).toBeVisible()
  const cookie = (await context.cookies()).find((item) => item.name.endsWith('admin_session'))!
  expect(cookie.httpOnly).toBe(true)
  expect(cookie.sameSite).toBe('Strict')
  if (process.env.TEST_PRODUCTION === '1') expect(cookie.secure).toBe(true)
  expect(await page.evaluate(() => document.cookie)).not.toContain(cookie.value)
  expect(await page.content()).not.toContain(cookie.value)
  expect(await page.content()).not.toContain('test-only-password')
  const html = await context.request.get('/')
  expect(await html.text()).not.toContain(cookie.value)
  await page.reload()
  await expect(page.getByRole('button', { name: 'Abmelden', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Abmelden', exact: true }).click()
  await expect(page.getByText('Test-Hafenbühne')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Anmelden', exact: true })).toBeVisible()
  expect(
    (await context.cookies()).filter((item) => item.name.endsWith('admin_session')),
  ).toHaveLength(0)
  expect(messages.join('\n')).not.toContain(cookie.value)
  expect(messages.join('\n')).not.toContain('test-only-password')
})

test('ordinary account gets 403 and an invalidated session clears previously loaded data', async ({
  page,
  context,
}) => {
  await page.goto('/')
  await page.getByLabel('Benutzername', { exact: true }).fill('ordinary')
  await page.getByLabel('Passwort', { exact: true }).fill('test-only-password')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.getByText('Zugriff gesperrt').first()).toBeVisible()
  await expect(page.getByText('Test-Hafenbühne')).toHaveCount(0)
  // Reauthenticate as the independently granted account.
  await page.reload()
  await page.getByRole('button', { name: 'Abmelden', exact: true }).click()
  await page.getByLabel('Benutzername', { exact: true }).fill('operator')
  await page.getByLabel('Passwort', { exact: true }).fill('test-only-password')
  await page.getByRole('button', { name: 'Anmelden', exact: true }).click()
  await expect(page.getByText('Test-Hafenbühne')).toBeVisible()
  const cookie = (await context.cookies()).find((item) => item.name.endsWith('admin_session'))!
  await context.addCookies([{ ...cookie, value: 'X'.repeat(43) }])
  await page.getByLabel('Zeitraum', { exact: true }).selectOption('today')
  await expect(page.getByText('Test-Hafenbühne')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Anmelden', exact: true })).toBeVisible()
})
