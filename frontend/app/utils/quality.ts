import type { Severity } from '#shared/contracts'

export const logoRules: Record<string, { label: string; severity: Severity; entityType?: string }> =
  {
    venue_missing_logo: { label: 'Orte ohne Logo', severity: 'warning', entityType: 'venue' },
    organization_missing_logo: {
      label: 'Organisationen ohne Logo',
      severity: 'warning',
      entityType: 'organization',
    },
    logo_unsupported_format: { label: 'Logos in anderem Format', severity: 'info' },
  }
