import { describe, expect, it } from 'vitest'
import { config, mount } from '@vue/test-utils'
import KpiCard from '../../app/components/KpiCard.vue'
import RequestState from '../../app/components/RequestState.vue'
import { failure } from '../../shared/errors'

config.global.stubs.NuxtLink = true
config.global.stubs.AppIcon = true

describe('dashboard display states', () => {
  it('renders zero and missing as different states', () => {
    const props = { label: 'Neu eingegangen', description: 'Im gewählten Zeitraum' }
    expect(mount(KpiCard, { props: { ...props, value: 0 } }).text()).toContain('0')
    expect(mount(KpiCard, { props }).text()).toContain('Nicht verfügbar')
  })
  it('labels retained data as stale and offers retry', async () => {
    const wrapper = mount(RequestState, {
      props: {
        loading: false,
        error: failure(503),
        hasData: true,
        lastSuccess: '2026-09-14T12:00:00Z',
      },
    })
    expect(wrapper.text()).toContain('veraltet')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })
})
