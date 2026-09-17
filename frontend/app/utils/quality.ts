import type { Severity } from '#shared/contracts'

export const qualityRules: Record<
  string,
  { label: string; severity: Severity; group: string; entityType?: string }
> = {
  venue_missing_logo: {
    label: 'Orte ohne Logo',
    severity: 'warning',
    group: 'Logos & Bilder',
    entityType: 'venue',
  },
  organization_missing_logo: {
    label: 'Organisationen ohne Logo',
    severity: 'warning',
    group: 'Logos & Bilder',
    entityType: 'organization',
  },
  logo_unsupported_format: {
    label: 'Logos in anderem Format',
    severity: 'info',
    group: 'Logos & Bilder',
  },
  postal_code_whitespace: {
    label: 'Postleitzahlen mit Leerzeichen',
    severity: 'warning',
    group: 'Adressqualität',
  },
}
