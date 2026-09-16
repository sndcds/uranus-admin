import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { statisticsFixture } from '../fixtures/statistics'
import { entityStatisticsResponseSchema } from '../../shared/contracts'
import {
  statisticsDelta,
  statisticsDateBoundary,
  statisticsActivityLink,
  statisticsOrder,
} from '../../app/utils/statistics'
import EntityTimelineChart from '../../app/components/statistics/EntityTimelineChart.vue'
import EntitySparkline from '../../app/components/statistics/EntitySparkline.vue'
import EntityDistributionChart from '../../app/components/statistics/EntityDistributionChart.vue'
import EntityMetricCard from '../../app/components/statistics/EntityMetricCard.vue'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'

describe('entity statistics', () => {
  it('validates complete, aligned, zero-filled series and rejects inconsistent responses', () => {
    expect(entityStatisticsResponseSchema.safeParse(statisticsFixture()).success).toBe(true)
    expect(
      entityStatisticsResponseSchema.safeParse(
        statisticsFixture(new URLSearchParams('compare=previous')),
      ).success,
    ).toBe(true)
    const mutations = [
      (data: ReturnType<typeof statisticsFixture>) => {
        data.series.pop()
      },
      (data: ReturnType<typeof statisticsFixture>) => {
        data.series[0]!.points[0]!.count = -1
      },
      (data: ReturnType<typeof statisticsFixture>) => {
        data.series[0]!.points[0]!.start_at = 'invalid'
      },
      (data: ReturnType<typeof statisticsFixture>) => {
        data.series[0]!.total++
      },
      (data: ReturnType<typeof statisticsFixture>) => {
        data.series[0]!.points.splice(1, 1)
      },
      (data: ReturnType<typeof statisticsFixture>) => {
        data.series[0]!.entity_type = 'unknown' as never
      },
      (data: ReturnType<typeof statisticsFixture>) => {
        data.series[0] = data.series[1]!
      },
      (data: ReturnType<typeof statisticsFixture>) => {
        data.recent[0]!.action.href = '//evil.test'
      },
      (data: ReturnType<typeof statisticsFixture>) => {
        data.series[0]!.previous_total = 0
      },
    ]
    for (const mutate of mutations) {
      const data = statisticsFixture()
      mutate(data)
      expect(entityStatisticsResponseSchema.safeParse(data).success).toBe(false)
    }
  })
  it('keeps percentage deltas finite and custom local days correct across DST', () => {
    expect(statisticsDelta(12, 0).label).toBe('+12 neu')
    expect(statisticsDelta(0, 0).label).toBe('±0')
    expect(statisticsDelta(5, 10).label).toBe('−50 %')
    for (const [day, hours] of [
      ['2026-03-29', 23],
      ['2026-10-25', 25],
    ] as const) {
      const start = Date.parse(statisticsDateBoundary(day, 'Europe/Berlin'))
      const end = Date.parse(statisticsDateBoundary(day, 'Europe/Berlin', true))
      expect(end - start).toBe(hours * 3600000)
    }
    expect(statisticsActivityLink(statisticsFixture()).query.creation_basis).toBe('statistics')
  })
  it('renders named series, integer axes, keyboard crosshair, toggles and responsive geometry', async () => {
    const disconnect = vi.fn()
    let resize: ResizeObserverCallback
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(callback: ResizeObserverCallback) {
          resize = callback
        }
        observe() {}
        disconnect = disconnect
      },
    )
    const data = statisticsFixture()
    const wrapper = mount(EntityTimelineChart, {
      props: {
        series: data.series,
        fromAt: data.from_at,
        toAt: data.to_at,
        timezone: data.timezone,
        selectedTypes: [...statisticsOrder],
        highlighted: null,
      },
    })
    expect(wrapper.findAll('.statistics-series')).toHaveLength(7)
    expect(wrapper.find('.statistics-x-axis').exists()).toBe(true)
    expect(wrapper.find('.statistics-y-axis').exists()).toBe(true)
    await wrapper.get('svg[role="img"]').trigger('keydown', { key: 'ArrowRight' })
    expect(wrapper.get('[role="status"]').text()).toContain('Veranstaltungen')
    await wrapper.get('.statistics-legend button').trigger('click')
    expect(wrapper.emitted('toggle')?.[0]).toEqual(['user'])
    await wrapper.setProps({ selectedTypes: ['user'] })
    expect(wrapper.findAll('.statistics-series')).toHaveLength(1)
    resize!([{ contentRect: { width: 360 } } as ResizeObserverEntry], {} as ResizeObserver)
    await wrapper.vm.$nextTick()
    expect(wrapper.get('svg[role="img"]').attributes('viewBox')).toContain('360')
    await wrapper.setProps({ selectedTypes: [] })
    expect(wrapper.text()).toContain('Wähle mindestens eine Serie')
    wrapper.unmount()
    expect(disconnect).toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
  it('renders total, shares series with sparklines and handles zero or single-point plots', () => {
    const data = statisticsFixture(new URLSearchParams('compare=previous'))
    const donut = mount(EntityDistributionChart, { props: { series: data.series } })
    expect(donut.findAll('path')).toHaveLength(7)
    expect(donut.findAll('li')).toHaveLength(7)
    donut.unmount()
    const zero = data.series.map((s) => ({
      ...s,
      total: 0,
      points: s.points.map((p) => ({ ...p, count: 0 })),
    }))
    const empty = mount(EntityDistributionChart, { props: { series: zero } })
    expect(empty.find('svg').exists()).toBe(false)
    expect(empty.text()).toContain('Keine neuen Entitäten')
    empty.unmount()
    for (const points of [[], zero[0]!.points, data.series[0]!.points.slice(0, 1)]) {
      const spark = mount(EntitySparkline, { props: { points, color: 'blue' } })
      expect(spark.html()).not.toContain('NaN')
      spark.unmount()
    }
    const card = mount(EntityMetricCard, { props: { series: data.series[0]!, selected: true } })
    expect(card.attributes('aria-pressed')).toBe('true')
    expect(card.text()).toContain('gegenüber vorherigem Zeitraum')
    card.unmount()
  })
  it('allows exact proxy route and parameters, rejecting duplicate keys and writes', async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify(statisticsFixture())))
    const input = {
      path: '/api/v1/statistics/entities',
      method: 'GET',
      query: new URLSearchParams('period=7d&compare=previous'),
      authorization: 'Bearer test',
      baseUrl: 'http://localhost:8000',
    }
    expect((await forwardAdminRequest(input, 'http://127.0.0.1:8000', fetcher)).status).toBe(200)
    for (const query of ['period=7d&period=24h', 'table=user', 'period[]=7d']) {
      expect(
        (
          await forwardAdminRequest(
            { ...input, query: new URLSearchParams(query) },
            'http://127.0.0.1:8000',
            fetcher,
          )
        ).status,
      ).toBe(422)
    }
    expect(
      (
        await forwardAdminRequest(
          { ...input, path: '/api/v1/statistics/private' },
          'http://127.0.0.1:8000',
          fetcher,
        )
      ).status,
    ).toBe(404)
    expect(
      (await forwardAdminRequest({ ...input, method: 'POST' }, 'http://127.0.0.1:8000', fetcher))
        .status,
    ).toBe(405)
  })
})
