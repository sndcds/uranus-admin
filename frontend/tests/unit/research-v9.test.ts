import { expect, it } from 'vitest'
import cases from '../fixtures/research-v9-parity.json' with { type: 'json' }
import { groupedExecutionResponse } from '../fixtures/research-grouping'
import { researchExecutionResponseSchema } from '../../shared/research-execution'

it.each(cases)('validates a normal response carrying executable v9 $name', ({ plan }) => {
  const base = groupedExecutionResponse()
  const response = {
    ...base,
    query: plan.original_query,
    plan: {
      ...base.plan,
      kind: plan.clarification === 'none' ? 'plan' : 'needs_clarification',
      plan,
      diagnostics: { ...base.plan.diagnostics, planner_intent: plan.intent },
    },
  }
  expect(researchExecutionResponseSchema.parse(response)).toEqual(response)
})

it('rejects unsupported constraints and mismatched clarification envelopes', () => {
  const base = groupedExecutionResponse()
  const plan = base.plan.plan
  for (const change of [
    { intent: 'knowledge' },
    { metric: { ...plan.metric, operation: 'duration' } },
    { metric: { ...plan.metric, operation: 'value', field: null } },
    { price: { mode: 'free' } },
    { clarification: 'needs_definition' },
    { clarification: 'needs_date' },
    {
      spatial: {
        relation: 'nearest',
        reference: 'user_location',
        radius_m: null,
        area_query: null,
        place_query: null,
      },
    },
    { filters: [{ field: 'start_time', operator: 'gt', value: '18:00:00', upper: null }] },
    { filters: [{ field: 'start_time', operator: 'gte', value: '18:00:00+02:00', upper: null }] },
    { sql: 'SELECT 1' },
  ]) {
    expect(
      researchExecutionResponseSchema.safeParse({
        ...base,
        plan: { ...base.plan, plan: { ...plan, ...change } },
      }).success,
    ).toBe(false)
  }
})

it('accepts the closed distinct count equivalent of an existing count', () => {
  const base = groupedExecutionResponse()
  expect(
    researchExecutionResponseSchema.safeParse({
      ...base,
      plan: {
        ...base.plan,
        plan: {
          ...base.plan.plan,
          intent: 'count',
          entity_type: 'venue',
          metric: { ...base.plan.plan.metric, operation: 'distinct_count', distinct_by: 'venue' },
          group_by: [],
          ordering: null,
          limit: null,
        },
        diagnostics: { ...base.plan.diagnostics, planner_intent: 'count' },
      },
    }).success,
  ).toBe(true)
})
