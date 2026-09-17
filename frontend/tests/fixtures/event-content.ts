import type { EventContentStatistics, EventContentRanking } from '../../shared/contracts'
export function eventContentFixture(params = new URLSearchParams()): EventContentStatistics {
  const period = (params.get('period') ?? '24h') as EventContentStatistics['period']
  const status = params.get('status') as EventContentStatistics['status']
  const total = status === 'cancelled' ? 0 : status === 'released' ? 8 : 10
  const compare = params.get('compare') === 'previous' && period !== 'all'
  const end = '2026-09-17T12:00:00Z'
  const days = { today: 14 / 24, '24h': 1, '7d': 7, '30d': 30, '90d': 90, all: 1 }[period]
  const start = new Date(Date.parse(end) - days * 86400000).toISOString()
  function coverage(count: number, denominator: number) {
    return {
      events_with_assignment: count,
      events_without_assignment: denominator - count,
      coverage_percent: denominator ? (count / denominator) * 100 : 0,
    }
  }
  const ranking = (id: string, name: string): EventContentRanking => ({
    distinct_assignment_count: total ? 1 : 0,
    items: total
      ? [
          {
            id,
            name,
            event_count: 6,
            event_share_percent: (6 / total) * 100,
            rank: 1,
            previous_rank: compare ? 3 : null,
            rank_delta: compare ? 2 : null,
            previous_event_count: compare ? 4 : null,
            count_delta: compare ? 2 : null,
            previous_share_percent: compare ? 40 : null,
            share_delta_percentage_points: compare ? (6 / total) * 100 - 40 : null,
          },
        ]
      : [],
  })
  const categories = ranking('1', 'Musik')
  const eventTypes = ranking('1', 'Konzert')
  if (total) {
    for (const [data, name, count] of [
      [categories, 'Familie', 2],
      [eventTypes, 'Workshop', total - 6],
    ] as const) {
      data.distinct_assignment_count = 2
      data.items.push({
        ...data.items[0]!,
        id: '2',
        name,
        rank: 2,
        event_count: count,
        event_share_percent: (count / total) * 100,
        previous_rank: compare ? 4 : null,
        rank_delta: compare ? 2 : null,
        previous_event_count: compare ? 2 : null,
        count_delta: compare ? count - 2 : null,
        previous_share_percent: compare ? 20 : null,
        share_delta_percentage_points: compare ? (count / total) * 100 - 20 : null,
      })
    }
  }
  return {
    period,
    status,
    from_at: period === 'all' ? null : start,
    to_at: period === 'all' ? null : end,
    timezone: 'Europe/Berlin',
    observed_at: end,
    event_count: total,
    coverage: {
      categories: coverage(total ? 8 : 0, total),
      genres: coverage(total ? 6 : 0, total),
      event_types: coverage(total, total),
    },
    categories,
    genres: ranking('1:4', 'Konzert · Rock'),
    event_types: eventTypes,
    comparison: compare
      ? {
          from_at: new Date(Date.parse(start) - days * 86400000).toISOString(),
          to_at: start,
          event_count: 10,
          coverage: {
            categories: coverage(8, 10),
            genres: coverage(6, 10),
            event_types: coverage(9, 10),
          },
        }
      : null,
  }
}
