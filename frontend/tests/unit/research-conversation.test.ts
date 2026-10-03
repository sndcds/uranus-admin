import { existsSync, readFileSync } from 'node:fs'
import { expect, it } from 'vitest'
import summary from '../fixtures/conversation-summary.json' with { type: 'json' }
import {
  researchConversationContextSchema,
  researchPlanSummarySchema,
} from '../../shared/research-conversation'
import { conversationContext, type ResearchTurn } from '../../app/utils/research-conversation'
import { executionResponse } from '../fixtures/research-execution'
import { groupedExecutionResponse } from '../fixtures/research-grouping'
import { researchQueryRequestSchema } from '../../shared/research-execution'

it('limits advisory memory to the four latest fully represented successful plans', () => {
  const turns: ResearchTurn[] = Array.from({ length: 8 }, (_, i) => ({
    id: i,
    question: `private question ${i}`,
    state: 'success',
    response: {
      ...executionResponse(),
      conversation_summary: researchPlanSummarySchema.parse({ ...summary, limit: i + 1 }),
    },
  }))
  const context = conversationContext(turns)!
  expect(context.previous_turns.map((t) => t.limit)).toEqual([5, 6, 7, 8])
  const json = JSON.stringify(context)
  expect(json).not.toMatch(
    /private question|answer_text|Für diese Auswahl|sql|provenance|latitude|longitude|entity_key|request_id/,
  )
  expect(new TextEncoder().encode(json).length).toBeLessThanOrEqual(8192)
  turns.push({ id: 9, question: 'private place', state: 'success', response: executionResponse() })
  expect(conversationContext(turns)).toBeUndefined()
  turns[turns.length - 1]!.state = 'clarification'
  expect(conversationContext(turns)).toBeUndefined()
})
it.each([
  'sql',
  'latitude',
  'longitude',
  'geometry',
  'entity_id',
  'question',
  'result',
  'answer_text',
])('rejects %s in context', (key) => {
  expect(researchPlanSummarySchema.safeParse({ ...summary, [key]: 'private' }).success).toBe(false)
})
it('bounds context and names; ordinary requests remain compatible', () => {
  expect(
    researchConversationContextSchema.safeParse({ previous_turns: Array(5).fill(summary) }).success,
  ).toBe(false)
  expect(
    researchPlanSummarySchema.safeParse({ ...summary, semantic_query: 'x'.repeat(161) }).success,
  ).toBe(false)
  expect(researchQueryRequestSchema.parse({ query: 'Eine Frage' })).toEqual({ query: 'Eine Frage' })
  expect(researchQueryRequestSchema.safeParse({ query: 'Eine Frage', plan: summary }).success).toBe(
    false,
  )
})
it('validates additive v11 successful and needs_context envelopes without accepting private metadata', async () => {
  const { default: cases } = await import('../fixtures/research-conversation-v11.json', {
    with: { type: 'json' },
  })
  const { researchExecutionResponseSchema } = await import('../../shared/research-execution')
  for (const item of cases) {
    const response = groupedExecutionResponse()
    const clarification = item.plan.clarification !== 'none'
    const value = {
      ...response,
      query: item.plan.original_query,
      answer_text: clarification ? null : response.answer_text,
      conversation_summary: clarification ? null : summary,
      plan: {
        ...response.plan,
        plan: item.plan,
        kind: clarification ? 'needs_clarification' : 'plan',
        schema_version: 'research-query-plan-v11',
        prompt_version: 'research-planner-v17',
        diagnostics: {
          ...response.plan.diagnostics,
          planner_prompt_version: 'research-planner-v17',
          planner_intent: item.plan.intent,
        },
      },
      ...(clarification
        ? {
            result: {
              kind: 'needs_clarification',
              reason: 'planner',
              planner_state: 'needs_context',
              field: null,
              query: null,
              candidates: [],
            },
          }
        : {}),
    }
    expect(researchExecutionResponseSchema.safeParse(value).success).toBe(true)
    expect(
      researchExecutionResponseSchema.safeParse({
        ...value,
        conversation_summary: { ...summary, latitude: 54.79 },
      }).success,
    ).toBe(false)
  }
})

it('keeps the authoritative answer builder outside the frontend', () => {
  const component = readFileSync('app/components/ResearchQueryAnswer.vue', 'utf8')
  expect(component).toContain('{{ response.answer_text }}')
  expect(component).not.toMatch(/summarizeResearchResult|research-summary|Math\.(max|min)/)
  expect(existsSync('app/utils/research-summary.ts')).toBe(false)
})
