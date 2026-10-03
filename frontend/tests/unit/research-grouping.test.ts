import { describe, expect, it } from 'vitest'
import { groupedExecutionResponse } from '../fixtures/research-grouping'
import {
  researchExecutionResponseSchema,
  groupedResultSchema,
} from '../../shared/research-execution'

const result = {
  kind: 'grouped',
  metric: 'occurrence_count',
  dimensions: ['event_type', 'month'],
  ordering: 'desc',
  limit: 20,
  items: [
    {
      coordinates: [
        { dimension: 'event_type', key: '2', name: 'Konzert' },
        { dimension: 'month', key: '09', name: '09' },
      ],
      value: 7,
    },
  ],
}
describe('ordered multidimensional results', () => {
  it('keeps taxonomy, month and occurrence count', () => {
    expect(groupedResultSchema.parse(result)).toEqual(result)
  })
  it('rejects losing, duplicating or reordering an axis', () => {
    for (const dimensions of [
      ['month'],
      ['event_type', 'event_type'],
      ['month', 'event_type'],
      ['sql'],
    ]) {
      expect(groupedResultSchema.safeParse({ ...result, dimensions }).success).toBe(false)
    }
  })
})

it('validates the complete normal execution envelope, including the v9 plan', () => {
  const response = groupedExecutionResponse()
  expect(researchExecutionResponseSchema.parse(response)).toEqual(response)
  for (const field of ['resolution', 'execution', 'observed_at', 'timezone', 'diagnostics']) {
    const missing = Object.fromEntries(Object.entries(response).filter(([key]) => key !== field))
    expect(researchExecutionResponseSchema.safeParse(missing).success).toBe(false)
  }
  for (const group_by of [['event_type', 'event_type'], ['sql'], 'venue']) {
    expect(
      researchExecutionResponseSchema.safeParse({
        ...response,
        plan: { ...response.plan, plan: { ...response.plan.plan, group_by } },
      }).success,
    ).toBe(false)
  }
  for (const change of [{ prompt_version: 'research-planner-v14' }, { extra: true }]) {
    expect(
      researchExecutionResponseSchema.safeParse({
        ...response,
        plan: { ...response.plan, ...change },
      }).success,
    ).toBe(false)
  }
})
