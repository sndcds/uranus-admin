import { loginRedirect } from '~/utils/auth-redirect'

export default defineNuxtPlugin({
  dependsOn: ['admin-api'],
  setup(nuxtApp) {
    const auth = useAuthStore()
    const router = useRouter()
    // Register once per Nuxt app, independent of layout mounts.
    nuxtApp.$adminApi.onAccessLost(() => {
      if (auth.status === 'anonymous') return
      const target = router.currentRoute.value
      auth.clear()
      if (target.path !== '/login')
        void nuxtApp.runWithContext(() =>
          navigateTo(loginRedirect(target.fullPath), { replace: true }),
        )
    })
  },
})
