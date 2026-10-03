import { researchQuestionSchema } from '#shared/contracts'

/** Legacy search URLs, including the bare search page, retain their behavior. */
export function researchAnswerMode(query: Record<string, unknown>) {
  return query.mode === 'answer' || Object.hasOwn(query, 'question')
}
export function researchAnswerQuery(query: Record<string, unknown>) {
  return researchQuestionSchema.safeParse(query.question)
}
export function researchAnswerUrl(question?: string) {
  return question === undefined ? {} : { question }
}
export const researchMetricLabels = {
  event_count: 'Veranstaltungen',
  occurrence_count: 'Termine',
  venue_count: 'Veranstaltungsorte',
  organization_count: 'Organisationen',
} as const

const monthLabels = new Map<string, string>([
  ['01', 'Januar'],
  ['02', 'Februar'],
  ['03', 'März'],
  ['04', 'April'],
  ['05', 'Mai'],
  ['06', 'Juni'],
  ['07', 'Juli'],
  ['08', 'August'],
  ['09', 'September'],
  ['10', 'Oktober'],
  ['11', 'November'],
  ['12', 'Dezember'],
])

const weekdayLabels = new Map<string, string>([
  ['1', 'Montag'],
  ['2', 'Dienstag'],
  ['3', 'Mittwoch'],
  ['4', 'Donnerstag'],
  ['5', 'Freitag'],
  ['6', 'Samstag'],
  ['7', 'Sonntag'],
])

/** Display cyclical calendar months without changing their API coordinates. */
export function formatGroupingCoordinate(dimension: string, value: string): string {
  if (dimension === 'weekday') return weekdayLabels.get(value) ?? value
  return dimension === 'month' ? (monthLabels.get(value) ?? value) : value
}
