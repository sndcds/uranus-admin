import { describe, expect, it } from 'vitest'
import { groupedResultSchema } from '../../shared/research-execution'

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
