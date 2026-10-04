import type { ResearchQueryResponse } from '#shared/contracts'
import type { ApiFailure } from '#shared/errors'

export const MAX_RESEARCH_TURNS = 20
export type ResearchTurn = {
  id: number
  question: string
  state: 'loading' | 'success' | 'error' | 'clarification' | 'cancelled'
  response?: ResearchQueryResponse
  error?: ApiFailure
  conversationId?: string
}

export function replaceClarificationTarget(
  original: string,
  query: string | null | undefined,
  candidate: string,
): string {
  if (!query) return original
  const index = original.indexOf(query)
  // Include overlapping matches: only an unambiguous literal target is editable.
  if (index < 0 || original.indexOf(query, index + 1) !== -1) return original
  return original.slice(0, index) + candidate + original.slice(index + query.length)
}
