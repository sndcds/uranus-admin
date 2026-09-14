import { createAdminApi } from '~/utils/admin-api'

export default defineNuxtPlugin(() => ({ provide: { adminApi: createAdminApi() } }))
