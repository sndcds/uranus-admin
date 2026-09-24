import type { Finding } from '#shared/contracts'
import { entityPresentation } from './activity'
import { qualityRuleLabel } from './quality'

export function findingRecordName(finding: Finding): string {
  const name = finding.entity_name.trim()
  return !name || name === finding.entity_key ? entityPresentation(finding.entity_type).label : name
}

export function findingRecordKey(finding: Finding): string | null {
  if (finding.entity_name.trim() && finding.entity_name.trim() !== finding.entity_key) return null
  const key = finding.entity_key
  return key.length > 32 ? `${key.slice(0, 16)}…${key.slice(-8)}` : key
}

export function findingAdditionalMessage(finding: Finding): string | null {
  // Suppress only repeated wording, never different evidence or details.
  const normalize = (value: string) =>
    value
      .toLocaleLowerCase('de')
      .replace(/\b(der|die|das|dem|den)\b/g, '')
      .replace(/[.,;:!?]/g, '')
      .replace(/\s+/g, ' ')
      .trim()
  return normalize(finding.message) === normalize(qualityRuleLabel(finding.rule))
    ? null
    : finding.message
}

const priorityReasonLabels: Record<string, string> = {
  severity_error: 'Schweregrad: Fehler',
  severity_warning: 'Schweregrad: Warnung',
  severity_info: 'Schweregrad: Hinweis',
  published: 'Veröffentlicht',
  published_soon: 'Veröffentlichter Termin steht bald bevor',
  upcoming_dates: 'Kommende Termine vorhanden',
}
export function findingPriorityReason(reason: string): string {
  return priorityReasonLabels[reason] ?? reason
}
