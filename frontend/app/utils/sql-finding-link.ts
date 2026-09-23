import type { Finding } from '#shared/contracts'
/** Only finding identity/filter state travels in the URL, never SQL or result data. */
export function sqlFindingLink(finding: Finding, mode: 'persisted' | 'live' = 'persisted'): string {
  const query = new URLSearchParams({
    mode,
    entity_type: finding.entity_type,
    entity_key: finding.entity_key,
    rule: finding.rule,
  })
  return `/findings?${query}#sql-editor=${encodeURIComponent(finding.id)}`
}
export function sqlFindingFromHash(hash: string, findings: Finding[]): Finding | undefined {
  if (!hash.startsWith('#sql-editor=') || hash.length > 25_000) return
  try {
    const id = decodeURIComponent(hash.slice('#sql-editor='.length))
    return findings.find((finding) => finding.id === id && finding.sql_diagnostic_available)
  } catch {
    return
  }
}
