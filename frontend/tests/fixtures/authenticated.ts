import { test as base, expect } from '@playwright/test'

// Real HttpOnly test sessions also reach SSR. Browser-only route mocks cannot
// authorize server rendering. The independent request fixture stays anonymous.
export const test = base.extend({
  page: async ({ page, context }, use) => {
    const response = await context.request.post('/api/admin/auth/login', {
      headers: { Origin: 'http://127.0.0.1:3100', 'X-Admin-CSRF': '1' },
      data: { login: 'operator', password: 'test-only-password' },
    })
    expect(response.status()).toBe(200)
    await use(page)
  },
})
export { expect }
