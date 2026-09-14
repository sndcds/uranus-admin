import tailwindcss from '@tailwindcss/vite'

export default defineNuxtConfig({
  compatibilityDate: '2026-09-14',
  modules: ['@pinia/nuxt', '@nuxt/eslint'],
  css: ['~/assets/css/main.css'],
  vite: { plugins: [tailwindcss()] },
  devtools: { enabled: false },
  typescript: { strict: true },
  runtimeConfig: {
    adminApiBase: 'http://127.0.0.1:8000',
    public: { allowDevTokenEntry: false },
  },
  app: {
    head: {
      htmlAttrs: { lang: 'de' },
      title: 'Kulturbytes · Administration',
      meta: [{ name: 'robots', content: 'noindex, nofollow' }],
    },
  },
  routeRules: {
    '/api/admin/**': { headers: { 'cache-control': 'private, no-store' } },
    '/**': { headers: { 'cache-control': 'private, no-store' } },
  },
})
