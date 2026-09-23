// Match the existing production test policy, plus the already approved public image origin.
// No application/deployment CSP is changed by this response-only test hook.
export async function enforceProductionCsp(page: import('@playwright/test').Page) {
  if (process.env.TEST_PRODUCTION !== '1') return
  await page.route('**/*', async (route) => {
    if (route.request().resourceType() !== 'document') return route.continue()
    const response = await route.fetch()
    await route.fulfill({
      response,
      headers: {
        ...response.headers(),
        'content-security-policy':
          "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://api.kulturbytes.de; connect-src 'self'; object-src 'none'; base-uri 'self'",
      },
    })
  })
}
