import type { MarkCreate, MarkUpdate } from '#shared/contracts'

export const markReasons: Record<MarkCreate['reasons'][number], string> = {
  questionable_content: 'Fragwürdiger Inhalt',
  low_quality: 'Geringe Qualität',
  incorrect: 'Falsche Angaben',
  incomplete: 'Unvollständige Angaben',
  outdated: 'Veraltet / nicht mehr gültig',
  duplicate: 'Duplikat',
  spam: 'Spam / unerwünschte Werbung',
  unsuitable: 'Unpassender Inhalt',
  rights_privacy: 'Rechte / Datenschutz prüfen',
  technical: 'Technisches Problem',
  other: 'Sonstiges',
}
export const markStatuses: Record<MarkUpdate['status'], string> = {
  open: 'Offen',
  in_progress: 'In Bearbeitung',
  done: 'Erledigt',
}
export const markUrgencies: Record<MarkCreate['urgency'], string> = {
  normal: 'Normal',
  high: 'Hoch',
  urgent: 'Dringend',
}
export const markEventLabels = {
  created: 'Markierung angelegt',
  updated: 'Markierung aktualisiert',
  completed: 'Als erledigt markiert',
  reopened: 'Wieder geöffnet',
}
