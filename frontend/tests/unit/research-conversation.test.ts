import { existsSync, readFileSync } from 'node:fs'
import { expect, it } from 'vitest'
import summary from '../fixtures/conversation-summary.json' with { type: 'json' }
import {
  researchConversationContextSchema,
  researchPlanSummarySchema,
} from '../../shared/research-conversation'
import { groupedExecutionResponse } from '../fixtures/research-grouping'
import { researchQueryRequestSchema } from '../../shared/research-execution'
import { replaceClarificationTarget } from '../../app/utils/research-conversation'

it.each([
  [
    'exactly one target',
    'Wie viele Veranstaltungen gab es in Neustadt im August?',
    'Neustadt',
    'Neustadt in Holstein',
    'Wie viele Veranstaltungen gab es in Neustadt in Holstein im August?',
  ],
  ['target at start', 'Jazz im August', 'Jazz', 'Smooth Jazz', 'Smooth Jazz im August'],
  ['target at end', 'Konzerte in Kiel', 'Kiel', 'Kiel-Mitte', 'Konzerte in Kiel-Mitte'],
  [
    'punctuation and spacing',
    '  In „Kiel“, im AUGUST? ',
    'Kiel',
    'Kiel-Mitte',
    '  In „Kiel-Mitte“, im AUGUST? ',
  ],
  ['empty target', 'Konzerte in Kiel', '', 'Berlin', 'Konzerte in Kiel'],
  ['null target', 'Konzerte in Kiel', null, 'Berlin', 'Konzerte in Kiel'],
  ['absent target', 'Konzerte in Kiel', 'Hamburg', 'Berlin', 'Konzerte in Kiel'],
  ['different casing', 'Konzerte in Kiel', 'kiel', 'Berlin', 'Konzerte in Kiel'],
  ['duplicate target', 'Kiel oder Kiel?', 'Kiel', 'Berlin', 'Kiel oder Kiel?'],
  ['overlapping targets', 'aaa', 'aa', 'b', 'aaa'],
  ['literal candidate', 'Konzerte in Kiel?', 'Kiel', 'A.*(B)[$&]$1', 'Konzerte in A.*(B)[$&]$1?'],
  ['literal query', 'Konzerte in A.*(B)?', 'A.*(B)', 'Kiel', 'Konzerte in Kiel?'],
] as const)(
  'edits a clarification draft safely: %s',
  (_name, original, query, candidate, expected) => {
    expect(replaceClarificationTarget(original, query, candidate)).toBe(expected)
  },
)

it('keeps semantic state ownership entirely in the backend', () => {
  const component = readFileSync('app/components/ResearchQuestion.vue', 'utf8')
  const helper = readFileSync('app/utils/research-conversation.ts', 'utf8')
  expect(component).not.toMatch(/conversationContext|conversation_summary|previous_turns/)
  expect(helper).not.toMatch(/previous_turns|researchPlanSummarySchema/)
  expect(component).toContain('conversation_id')
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
