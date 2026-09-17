import { returnTarget, loginRedirect } from '~/utils/auth-redirect'

export default defineNuxtRouteMiddleware(async (to) => {
  const auth = useAuthStore()
  await auth.checkSession()
  if (to.meta.public === true) {
    if (to.path === '/login' && auth.isAdmin)
      return navigateTo(returnTarget(to.query.redirect, to.hash), { replace: true })
    return
  }
  if (!auth.isAdmin) return navigateTo(loginRedirect(to.fullPath), { replace: true })
})
