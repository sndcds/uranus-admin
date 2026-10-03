import { expect, it } from 'vitest'
import cases from '../fixtures/research-modern-v12.json' with { type: 'json' }
import context from '../fixtures/conversation-v12-context.json' with { type: 'json' }
import { modernPlanResponseSchema } from '../../shared/research-grouping'
import {
  researchConversationContextSchema,
  researchPlanSummarySchema,
} from '../../shared/research-conversation'
import { researchQueryRequestSchema } from '../../shared/research-execution'
import { conversationContext, type ResearchTurn } from '../../app/utils/research-conversation'
import { executionResponse } from '../fixtures/research-execution'

it.each(cases)('accepts the combined v12 $name contract', (item) => {
  const response = {
    kind: item.plan.clarification === 'none' ? 'plan' : 'needs_clarification',
    schema_version: 'research-query-plan-v12',
    prompt_version: 'research-planner-v18',
    model: 'fixture',
    plan: item.plan,
    reference_date: '2026-10-03',
    timezone: 'Europe/Berlin',
    diagnostics: {
      request_id: 'a'.repeat(32),
      planner_intent: item.plan.intent,
      planner_model: 'fixture',
      planner_prompt_version: 'research-planner-v18',
      planner_ms: 1,
      total_ms: 1,
    },
  }
  expect(modernPlanResponseSchema.parse(response).plan).toEqual(item.plan)
})
it('retains the district expectation in the next conversation request without private data', () => {
  const summary = researchPlanSummarySchema.parse(context.previous_turns[0])
  const turns: ResearchTurn[] = [
    {
      id: 1,
      question: 'Veranstaltungen im Kreis Schleswig-Flensburg',
      state: 'success',
      response: { ...executionResponse(), conversation_summary: summary },
    },
  ]
  const next = conversationContext(turns)
  expect(next).toEqual(context)
  expect(
    researchQueryRequestSchema.parse({ query: 'Und nur sonntags?', conversation_context: next }),
  ).toEqual({ query: 'Und nur sonntags?', conversation_context: context })
  expect(JSON.stringify(next)).not.toMatch(
    /sql|parameters|geometry|coordinates|entity_id|answer_text/,
  )
})
it.each([
  'sql',
  'id',
  'geometry',
  'latitude',
  'longitude',
  'parent_id',
  'osm_id',
  'ags',
  'iso_code',
])('rejects %s in area summaries', (key) => {
  const value = structuredClone(context)
  Object.assign(value.previous_turns[0]!.areas[0]!, { [key]: 'private' })
  expect(researchConversationContextSchema.safeParse(value).success).toBe(false)
})
it('keeps the four-predicate, four-summary and closed-level bounds', () => {
  const value = structuredClone(context)
  value.previous_turns[0]!.areas = Array.from({ length: 4 }, (_, i) => ({
    name: `Kreis ${i}`,
    relation: 'inside',
    expected_level: 'district',
  }))
  expect(researchConversationContextSchema.safeParse(value).success).toBe(true)
  value.previous_turns[0]!.areas.push({
    name: 'Fifth',
    relation: 'inside',
    expected_level: 'district',
  })
  expect(researchConversationContextSchema.safeParse(value).success).toBe(false)
  expect(
    researchConversationContextSchema.safeParse({
      previous_turns: Array(5).fill(context.previous_turns[0]),
    }).success,
  ).toBe(false)
  const bad = structuredClone(context)
  bad.previous_turns[0]!.areas[0]!.expected_level = 'official-code'
  expect(researchConversationContextSchema.safeParse(bad).success).toBe(false)
})
