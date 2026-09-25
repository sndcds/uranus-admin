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

it.each([
  [504, 'live_findings_timeout', 'Abruf dauert zu lange'],
  [504, 'request_timeout', 'Abruf dauert zu lange'],
  [502, 'invalid_response', 'Abruf fehlgeschlagen'],
  [502, 'network_error', 'Abruf fehlgeschlagen'],
  [401, 'request_failed', 'Zugang erforderlich'],
  [403, 'request_failed', 'Zugriff gesperrt'],
] as const)('RequestState renders %s/%s distinctly', (status, code, title) => {
  const detail = failure(status, code)
  const view = mount(RequestState, { props: { loading: false, error: detail } })
  expect(view.text()).toContain(title)
  expect(view.text()).toContain(detail.message)
})
