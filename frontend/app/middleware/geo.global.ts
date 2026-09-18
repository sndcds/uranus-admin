import { geoScopeIdSchema } from '#shared/contracts'
import { asFailure, failure } from '#shared/errors'
import { supportsGeoScope } from '~/utils/geo'

/** Runs after auth: URL > session store > no scope, before any list request. */
export default defineNuxtRouteMiddleware(async (to) => {
  const auth = useAuthStore()
  if (!auth.isAdmin || !supportsGeoScope(to.path)) return
  const preferences = useFilterPreferencesStore()
  const explicit = Object.hasOwn(to.query, 'geo_scope_id')
  if (explicit) {
    const parsed = geoScopeIdSchema.safeParse(to.query.geo_scope_id)
    const revision = auth.revision
    let remove = !parsed.success
    if (!parsed.success) {
      preferences.setGeoScope(null)
      preferences.geoScopeError = 'Der Gebietsfilter in der URL ist ungültig und wurde entfernt.'
    } else if (preferences.sharedGeoScope?.id !== parsed.data) {
      preferences.setGeoScope(null)
      const geoRevision = preferences.geoRevision
      try {
        const area = await useNuxtApp().$adminApi.geoArea(parsed.data)
        if (auth.revision !== revision || !auth.isAdmin || preferences.geoRevision !== geoRevision)
          return
        preferences.setGeoScope(area)
      } catch (cause) {
        if (auth.revision !== revision || !auth.isAdmin || preferences.geoRevision !== geoRevision)
          return
        const error = asFailure(cause)
        preferences.geoScopeError = error.message
        remove = error.code === 'geo_scope_not_found'
        if (remove) preferences.geoScopeError = failure(404, 'geo_scope_not_found').message
      }
    }
    if (remove) {
      // Keep the warning in the SSR payload; a server redirect starts a new Pinia instance.
      // Hydration removes the invalid URL in the browser while retaining that warning.
      if (import.meta.server) return
      const query = { ...to.query }
      delete query.geo_scope_id
      return navigateTo({ path: to.path, query, hash: to.hash }, { replace: true })
    }
  } else if (preferences.sharedGeoScope) {
    return navigateTo(
      {
        path: to.path,
        query: { ...to.query, geo_scope_id: preferences.sharedGeoScope.id },
        hash: to.hash,
      },
      { replace: true },
    )
  }
})
