import { defineConfig, devices } from '@playwright/test'

const production = process.env.TEST_PRODUCTION === '1'

export default defineConfig({
  testDir: './tests/e2e',
  // A cold Vite server compiles pages and dependencies on demand.
  timeout: production ? 30000 : 90000,
  expect: { timeout: production ? 20000 : 45000 },
  use: { baseURL: 'http://127.0.0.1:3100', trace: 'retain-on-failure' },
  projects: [
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1100 } },
    },
    {
      name: 'mobile',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
      },
    },
  ],
  webServer: [
    {
      // Isolated component fixture; CI's browser container has Node but no pnpm.
      command:
        'node node_modules/vite/bin/vite.js --config tests/fixtures/operations/vite.config.ts',
      url: 'http://127.0.0.1:3101',
      reuseExistingServer: false,
    },
    {
      command: 'node tests/fixtures/auth-server.mjs',
      url: 'http://127.0.0.1:31902/health',
      reuseExistingServer: false,
    },
    {
      command: production
        ? 'node .output/server/index.mjs'
        : 'pnpm exec nuxt dev --host 127.0.0.1 --port 3100',
      env: {
        NUXT_ADMIN_API_BASE: 'http://127.0.0.1:31902',
        // Exercise the default provider; requests are intercepted before network access.
        NUXT_PUBLIC_MAP_TILE_ATTRIBUTION: 'Synthetische Testkacheln',
        NUXT_PUBLIC_MAP_TILE_ATTRIBUTION_URL: '',
        NITRO_HOST: '127.0.0.1',
        NITRO_PORT: '3100',
        // Production must remove the manual credential UI even if this flag is set.
        NUXT_PUBLIC_ALLOW_DEV_TOKEN_ENTRY: production ? 'true' : 'false',
      },
      url: 'http://127.0.0.1:3100',
      reuseExistingServer: false,
      timeout: 120000,
    },
  ],
})
