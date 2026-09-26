import { workspaceTarget, loginRedirect } from '~/utils/auth-redirect'

export default defineNuxtRouteMiddleware(async (to) => {
  const auth = useAuthStore()
  await auth.checkSession()
  if (to.meta.public === true) {
    if (to.path === '/login' && auth.canResearch)
      return navigateTo(workspaceTarget(to.query.redirect, to.hash, auth.isAdmin), {
        replace: true,
      })
    return
  }
  if (!auth.canResearch) return navigateTo(loginRedirect(to.fullPath), { replace: true })
  if (!auth.isAdmin && !/^\/research(?:\/|$)/.test(to.path))
    return navigateTo('/research', { replace: true })
})
