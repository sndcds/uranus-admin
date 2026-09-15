import { z } from 'zod'

// Run during module evaluation, before importing modules construct their schemas.
// A Nuxt plugin callback would run after its static schema imports have evaluated.
z.config({ jitless: true })

export { z }
