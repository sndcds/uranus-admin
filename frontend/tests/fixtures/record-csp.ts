// Match the existing production test policy, plus the already approved public image origin.
// No application/deployment CSP is changed by this response-only test hook.
export async function enforceProductionCsp(page: import('@playwright/test').Page) {
  if (process.env.TEST_PRODUCTION !== '1') return
  await page.route('**/*', async (route) => {
    if (route.request().resourceType() !== 'document') return route.continue()
    // Let the browser follow redirects so Secure loopback session cookies retain
    // their normal browser handling on legacy URL redirects.
    const response = await route.fetch({ maxRedirects: 0 })
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
