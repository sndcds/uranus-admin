import tailwindcss from '@tailwindcss/vite'

export default defineNuxtConfig({
  compatibilityDate: '2026-09-14',
  modules: ['@pinia/nuxt', '@nuxt/eslint'],
  css: ['~/assets/css/main.css'],
  vite: {
    plugins: [tailwindcss()],
    // Prebundle these CJS entry points in dev to avoid a full-page optimizer reload
    // on first opening the lazy editor. Production/client loading remains lazy.
    optimizeDeps: { include: ['prismjs/components/prism-core', 'prismjs/components/prism-sql'] },
  },
  devtools: { enabled: false },
  typescript: { strict: true },
  runtimeConfig: {
    adminApiBase: 'http://127.0.0.1:8000',
    trustedIngressIps: '',
    public: { allowDevTokenEntry: false },
  },
  app: {
    head: {
      htmlAttrs: { lang: 'de' },
      title: 'Kulturbytes · Administration',
      link: [{ rel: 'icon', type: 'image/x-icon', href: '/favicon.ico' }],
      meta: [{ name: 'robots', content: 'noindex, nofollow' }],
    },
  },
  routeRules: {
    '/api/admin/**': { headers: { 'cache-control': 'private, no-store' } },
    '/**': { headers: { 'cache-control': 'private, no-store' } },
  },
})
