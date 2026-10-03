import type { ResearchExecutionResponse } from '#shared/contracts'
import type { ApiFailure } from '#shared/errors'
import {
  researchConversationContextSchema,
  type ResearchConversationContext,
} from '#shared/research-conversation'

export const MAX_RESEARCH_TURNS = 20
export type ResearchTurn = {
  id: number
  question: string
  state: 'loading' | 'success' | 'error' | 'clarification' | 'cancelled'
  response?: ResearchExecutionResponse
  error?: ApiFailure
  context?: ResearchConversationContext
}
export function conversationContext(
  turns: ResearchTurn[],
): ResearchConversationContext | undefined {
  const summaries = []
  for (const turn of [...turns].reverse()) {
    // Never silently drop an unrepresentable/private or unsuccessful latest subject.
    if (turn.state !== 'success' || !turn.response?.conversation_summary) break
    summaries.unshift(turn.response.conversation_summary)
    if (summaries.length === 4) break
  }
  while (summaries.length) {
    const parsed = researchConversationContextSchema.safeParse({ previous_turns: summaries })
    if (parsed.success) return parsed.data
    summaries.shift()
  }
}
