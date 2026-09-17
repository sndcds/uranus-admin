import { createAdminApi } from '~/utils/admin-api'

export default defineNuxtPlugin({
  name: 'admin-api',
  setup() {
    // Nitro's request-scoped fetch forwards the incoming cookie during SSR.
    // Native preserves Response/status handling, including 401, in our API client.
    const fetcher = import.meta.server ? useRequestEvent()!.fetch : fetch
    return { provide: { adminApi: createAdminApi(fetcher) } }
  },
})
