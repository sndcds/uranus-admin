import { describe, expect, it } from 'vitest'
import { formatGroupingCoordinate } from '../../app/utils/research-answer'
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
describe('grouping coordinate display', () => {
  it.each([
    ['01', 'Januar'],
    ['02', 'Februar'],
    ['03', 'März'],
    ['04', 'April'],
    ['05', 'Mai'],
    ['06', 'Juni'],
    ['07', 'Juli'],
    ['08', 'August'],
    ['09', 'September'],
    ['10', 'Oktober'],
    ['11', 'November'],
    ['12', 'Dezember'],
  ])('displays month %s as %s', (value, label) => {
    expect(formatGroupingCoordinate('month', value)).toBe(label)
  })

  it.each(['00', '13', '1', ' 01', '01 ', '2026-01', 'unknown', '', 'toString', '__proto__'])(
    'preserves unrecognized month value %j without coercion',
    (value) => {
      expect(formatGroupingCoordinate('month', value)).toBe(value)
    },
  )

  it.each(['event_type', 'genre', 'category', 'venue', 'organization', 'municipality'])(
    'preserves names for %s, even when they look like month keys',
    (dimension) => {
      for (const value of ['Konzert', 'Jazz', 'Kunst', '01', '10']) {
        expect(formatGroupingCoordinate(dimension, value)).toBe(value)
      }
    },
  )
})

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
  for (const field of [
    'resolution',
    'execution',
    'observed_at',
    'timezone',
    'diagnostics',
    'sql_provenance',
  ]) {
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
