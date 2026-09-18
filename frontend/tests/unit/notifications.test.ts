import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import Page from '../../app/pages/notifications/index.vue'
import Detail from '../../app/pages/notifications/[id].vue'
import Delivery from '../../app/pages/notifications/deliveries/[id].vue'
import Preview from '../../app/components/NotificationPreview.vue'
import PageHeader from '../../app/components/PageHeader.vue'
import FilterBar from '../../app/components/FilterBar.vue'
import DataListShell from '../../app/components/DataListShell.vue'
import ResultSummary from '../../app/components/ResultSummary.vue'
import EmptyState from '../../app/components/EmptyState.vue'
import PaginationBar from '../../app/components/PaginationBar.vue'
import {
  notification,
  notificationPage,
  notificationDetail,
  notificationDeliveryDetail,
  notificationPreview,
} from '../fixtures/notifications'
import { createAdminApi } from '../../app/utils/admin-api'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'
const api = {
  notifications: vi.fn(),
  notification: vi.fn(),
  notificationDelivery: vi.fn(),
  notificationPreview: vi.fn(),
}
const global = {
  components: { PageHeader, FilterBar, DataListShell, ResultSummary, EmptyState, PaginationBar },
  stubs: {
    NuxtLink: { template: '<a><slot /></a>' },
    RequestState: true,
    NotificationPreview: true,
    AppIcon: true,
  },
}
beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
  vi.stubGlobal('useRoute', () => ({ params: { id: notification.id } }))
  api.notifications.mockResolvedValue(structuredClone(notificationPage))
  api.notification.mockResolvedValue(structuredClone(notificationDetail))
  api.notificationDelivery.mockResolvedValue(structuredClone(notificationDeliveryDetail))
  api.notificationPreview.mockImplementation((_id, locale) =>
    Promise.resolve(notificationPreview(locale)),
  )
})
afterEach(() => vi.unstubAllGlobals())
describe('notification administration', () => {
  it('lists organization and lifecycle, dry run and counts', async () => {
    const view = mount(Page, { global })
    await flushPromises()
    for (const value of [
      'Benachrichtigungen',
      'Kulturabend',
      'Kulturverein',
      'Dry Run',
      'Aktiv',
      'Heute gesendet',
      'Fehlgeschlagen',
    ])
      expect(view.text()).toContain(value)
    expect(view.text()).not.toContain('recipient@example.test')
    view.unmount()
  })
  it('sends filters through the typed API', async () => {
    const view = mount(Page, { global })
    await flushPromises()
    await view.findAll('select')[0]!.setValue('suppressed')
    await view.findAll('select')[1]!.setValue('quality_finding')
    await view.find('form').trigger('submit')
    await flushPromises()
    expect(api.notifications).toHaveBeenLastCalledWith(
      expect.objectContaining({
        status: 'suppressed',
        notification_type: 'quality_finding',
        page: 1,
      }),
    )
    view.unmount()
  })
  it('shows empty state and source/config errors', async () => {
    api.notifications.mockResolvedValue({
      ...notificationPage,
      items: [],
      health: {
        ...notificationPage.health,
        source_capability: false,
        config_issues: [
          {
            organization_id: notification.organization_id,
            organization_name: 'Verein',
            code: 'invalid_config',
          },
        ],
      },
    })
    const view = mount(Page, { global })
    await flushPromises()
    expect(view.text()).toContain('Keine Benachrichtigungen')
    expect(view.text()).toContain('Source-Schema nicht verfügbar')
    expect(view.text()).toContain('Ungültige Benachrichtigungskonfiguration: Verein')
    view.unmount()
  })
  it('shows detail and failed delivery history', async () => {
    const view = mount(Detail, { global })
    await flushPromises()
    expect(view.text()).toContain('Versandhistorie')
    expect(view.text()).toContain('Fehlgeschlagen · recipient@example.test')
    expect(view.text()).toContain('smtp_451')
    expect(view.text()).toContain('DA · Erster Hinweis')
    view.unmount()
  })
  it('shows sent delivery detail and included notifications', async () => {
    api.notificationDelivery.mockResolvedValue({
      ...notificationDeliveryDetail,
      status: 'sent',
      sent_at: notification.first_detected_at,
      last_error: null,
    })
    const view = mount(Delivery, { global })
    await flushPromises()
    expect(view.text()).toContain('Gesendet')
    expect(view.text()).toContain('Enthaltene Hinweise')
    expect(view.text()).toContain('Kulturabend')
    view.unmount()
  })
  for (const locale of ['de', 'da', 'en'] as const)
    it(`previews ${locale} safely`, async () => {
      const view = mount(Preview, { props: { notificationId: notification.id }, global })
      await view.find('select').setValue(locale)
      await view.find('button').trigger('click')
      await flushPromises()
      expect(view.text()).toContain(notificationPreview(locale).subject)
      expect(view.find('iframe').attributes('sandbox')).toBe('')
      expect(view.find('iframe').attributes('srcdoc')).toContain('Content-Security-Policy')
      await view
        .findAll('button')
        .find((b) => b.text() === 'Text')!
        .trigger('click')
      expect(view.find('pre').attributes('lang')).toBe(locale)
      expect(view.text()).toContain('Kulturverein')
      view.unmount()
    })
  it('requires credentials at proxy and permits only reads', async () => {
    const input = { path: '/api/v1/notifications', method: 'GET', query: new URLSearchParams() }
    expect((await forwardAdminRequest(input, 'http://backend')).status).toBe(401)
    expect(
      (
        await forwardAdminRequest(
          { ...input, authorization: 'Bearer token', method: 'POST' },
          'http://backend',
        )
      ).status,
    ).toBe(405)
  })
  it('validates API response and uses protected proxy', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(notificationPage)))
    const client = createAdminApi(fetcher)
    expect((await client.notifications({ status: 'active' })).items[0]?.id).toBe(notification.id)
    expect(fetcher.mock.calls[0]![0]).toBe('/api/admin/api/v1/notifications?status=active')
  })
})
