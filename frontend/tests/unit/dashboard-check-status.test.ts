import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DashboardCheckStatus from '../../app/components/DashboardCheckStatus.vue'
import StatusBadge from '../../app/components/StatusBadge.vue'
import { dateTime } from '../../app/utils/presentation'
const successful = {
  id: '00000000-0000-4000-8000-000000000001',
  status: 'success' as const,
  started_at: '2026-09-16T08:00:00Z',
  finished_at: '2026-09-16T08:10:00Z',
  finding_count: 7,
  rule_count: 19,
}
const global = {
  components: { StatusBadge },
  stubs: { NuxtLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } },
}
describe('dashboard check history', () => {
  it('distinguishes no stored runs from unavailable history', () => {
    expect(mount(DashboardCheckStatus, { global }).text()).toContain('Nicht verfügbar')
    expect(
      mount(DashboardCheckStatus, {
        props: { status: { latest_run: null, last_successful_run: null } },
        global,
      }).text(),
    ).toContain('Noch keine Prüfläufe')
  })
  it.each([
    ['success', 'Erfolgreich'],
    ['failed', 'Fehlgeschlagen'],
    ['queued', 'Wartet'],
    ['running', 'Läuft'],
  ] as const)('shows %s independently of the last success', (status, label) => {
    const wrapper = mount(DashboardCheckStatus, {
      props: {
        status: {
          latest_run: { ...successful, status, started_at: '2026-09-16T09:00:00Z' },
          last_successful_run: successful,
        },
      },
      global,
    })
    expect(wrapper.text()).toContain(label)
    expect(wrapper.text()).toContain(
      `Letzter erfolgreicher Lauf: ${dateTime(successful.finished_at)}`,
    )
    expect(wrapper.get('a').attributes('href')).toBe('/checks')
  })
})
