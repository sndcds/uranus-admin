import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '~': fileURLToPath(new URL('./app', import.meta.url)),
      '#shared': fileURLToPath(new URL('./shared', import.meta.url)),
    },
  },
  test: {
    environment: 'happy-dom',
    include: ['tests/unit/**/*.test.ts'],
    setupFiles: ['tests/unit/setup.ts'],
  },
})
