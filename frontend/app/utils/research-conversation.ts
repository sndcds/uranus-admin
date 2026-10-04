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
