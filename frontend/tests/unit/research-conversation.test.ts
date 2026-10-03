import { expect, it } from 'vitest'
import summary from '../fixtures/conversation-summary.json' with { type: 'json' }
import {
  researchConversationContextSchema,
  researchPlanSummarySchema,
} from '../../shared/research-conversation'
import { conversationContext, type ResearchTurn } from '../../app/utils/research-conversation'
import { summarizeResearchResult } from '../../app/utils/research-summary'
import { researchEvent } from '../fixtures/research'
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
    /private question|sql|provenance|latitude|longitude|entity_key|request_id/,
  )
  expect(new TextEncoder().encode(json).length).toBeLessThanOrEqual(8192)
  turns.push({ id: 9, question: 'private place', state: 'success', response: executionResponse() })
  expect(conversationContext(turns)).toBeUndefined()
  turns[turns.length - 1]!.state = 'clarification'
  expect(conversationContext(turns)).toBeUndefined()
})
it.each(['sql', 'latitude', 'longitude', 'geometry', 'entity_id', 'question', 'result'])(
  'rejects %s in context',
  (key) => {
    expect(researchPlanSummarySchema.safeParse({ ...summary, [key]: 'private' }).success).toBe(
      false,
    )
  },
)
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
it.each(['count', 'records', 'aggregate', 'comparison'] as const)(
  'summarizes %s using only the returned values',
  (kind) => {
    const response = executionResponse(kind)
    const text = summarizeResearchResult(response)!
    expect(text.endsWith('.')).toBe(true)
    if (kind === 'count') expect(text).toContain('123 Veranstaltungen')
    if (kind === 'records') expect(text).toContain('1 passende Datensätze')
    if (kind === 'aggregate') expect(text).toContain('„Kulturhaus“ mit 42 Veranstaltungen')
    if (kind === 'comparison') expect(text).toContain('„Kiel“ mit 156 Veranstaltungen')
  },
)
it('summarizes grouped display coordinates and ties without claiming causality or overall ranking', () => {
  const response = groupedExecutionResponse()
  expect(summarizeResearchResult(response)).toContain('„Konzert / September“ mit 7 Termine')
  if (response.result.kind !== 'grouped') throw Error('fixture')
  response.result.items.push({ ...response.result.items[0]! })
  expect(summarizeResearchResult(response)).toContain('2 der angezeigten Kombinationen teilen sich')
})
it('handles semantic, taxonomy, spatial and empty results without fabricating totals', () => {
  const response = executionResponse('records', true)
  expect(summarizeResearchResult(response)).toContain('keine vollständige Zählung')
  response.result = { kind: 'taxonomy', taxonomy: 'genre', items: [], total: 18 }
  expect(summarizeResearchResult(response)).toContain('18 unterschiedliche Genres')
  response.result = {
    kind: 'spatial',
    spatial_metric: 'longitude',
    ordering: 'asc',
    items: [researchEvent],
  }
  expect(summarizeResearchResult(response)).toContain('1 Datensätze mit bekannter Position')
  response.result.items = []
  expect(summarizeResearchResult(response)).toContain(
    'keine ausreichend passenden semantischen Treffer',
  )
  const empty = executionResponse('records')
  if (empty.result.kind !== 'records') throw Error('fixture')
  empty.result.items = []
  expect(summarizeResearchResult(empty)).toContain('keine passenden Ergebnisse')
  expect(summarizeResearchResult(executionResponse('needs_clarification'))).toBeNull()
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
