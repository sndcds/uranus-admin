import { researchQuestionSchema } from '#shared/contracts'

/** Legacy search URLs, including the bare search page, retain their behavior. */
export function researchAnswerMode(query: Record<string, unknown>) {
  return query.mode === 'answer' || Object.hasOwn(query, 'question')
}
export function researchAnswerQuery(query: Record<string, unknown>) {
  return researchQuestionSchema.safeParse(query.question)
}
export function researchAnswerUrl(question?: string) {
  return { mode: 'answer', ...(question === undefined ? {} : { question }) }
}
export const researchMetricLabels = {
  event_count: 'Veranstaltungen',
  occurrence_count: 'Termine',
  venue_count: 'Veranstaltungsorte',
  organization_count: 'Organisationen',
} as const
