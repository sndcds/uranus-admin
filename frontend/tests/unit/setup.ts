import { config } from '@vue/test-utils'

// Page tests isolate the independent, on-demand provenance feature. Its own
// component tests and browser flows exercise the real button and drawer.
config.global.stubs.SqlProvenanceButton = true
