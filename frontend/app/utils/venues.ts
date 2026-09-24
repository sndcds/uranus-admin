import type { VenueScope } from '#shared/contracts'

// Explicit Admin presentation, not Uranus terminology or a quality judgement.
export const venueScopeLabels = {
  organization: 'Provisorischer Ort (nicht eigener Ort)',
  shared: 'Eigener Ort',
} as const satisfies Record<VenueScope, string>
