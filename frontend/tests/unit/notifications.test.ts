import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import { AdminApiError, failure } from '../../shared/errors'
import DeliveryList from '../../app/pages/notifications/deliveries/index.vue'
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
  notificationGuidance,
  notificationDeliveryPage,
} from '../fixtures/notifications'
import { createAdminApi } from '../../app/utils/admin-api'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'
const api = {
  notifications: vi.fn(),
  notification: vi.fn(),
  notificationDelivery: vi.fn(),
  notificationDeliveries: vi.fn(),
  retryNotificationDelivery: vi.fn(),
  notificationPreview: vi.fn(),
}
const route = reactive({
  params: { id: notification.id },
  query: {} as Record<string, string | undefined>,
  fullPath: '',
})
const navigate = vi.fn()
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
  route.params.id = notification.id
  route.query = {}
  route.fullPath = ''
  vi.stubGlobal('useRoute', () => route)
  vi.stubGlobal('navigateTo', navigate)
  vi.stubGlobal('useRouter', () => ({
    push: async ({ query }: { query: Record<string, string | undefined> }) => {
      route.query = Object.fromEntries(
        Object.entries(query).filter(([, value]) => value !== undefined),
      )
      route.fullPath = JSON.stringify(query)
    },
  }))
  vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function () {
    this.open = true
  })
  vi.spyOn(HTMLDialogElement.prototype, 'close').mockImplementation(function () {
    this.open = false
  })
  api.notificationDeliveries.mockResolvedValue(structuredClone(notificationDeliveryPage))
  api.notifications.mockResolvedValue(structuredClone(notificationPage))
  api.notification.mockResolvedValue(structuredClone(notificationDetail))
  api.notificationDelivery.mockResolvedValue(structuredClone(notificationDeliveryDetail))
  api.notificationPreview.mockImplementation((_id, locale) =>
    Promise.resolve(notificationPreview(locale)),
  )
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})
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
      'Dauerhaft fehlgeschlagen',
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
    expect(view.text()).toContain('Temporär fehlgeschlagen')
    expect(view.text()).toContain('recipient@example.test')
    expect(view.text()).toContain('smtp_451')
    expect(view.text()).toContain('DA · Versuche: 1')
    expect(view.text()).toContain('Erster Hinweis')
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
      const html = view.find('iframe').attributes('srcdoc')!
      expect(html).toContain(notification.payload.external_action_url)
      expect(html).not.toContain('https://admin.kulturbytes.de')
      expect(html).not.toContain('/findings')
      expect(html).toContain('style-src &apos;unsafe-inline&apos;')
      // Only the additional preview CSP differs; the email markup/CSS is untouched.
      expect(html.replace(/<meta http-equiv="Content-Security-Policy"[^>]*>/, '')).toBe(
        notificationPreview(locale).html,
      )
      await view
        .findAll('button')
        .find((b) => b.text() === 'Text')!
        .trigger('click')
      expect(view.find('pre').attributes('lang')).toBe(locale)
      expect(view.text()).toContain('Kulturverein')
      view.unmount()
    })
  for (const locale of ['de', 'da', 'en'] as const)
    it(`previews ${locale} guidance without a replacement admin link`, async () => {
      api.notificationPreview.mockResolvedValue(notificationPreview(locale, false))
      const view = mount(Preview, { props: { notificationId: notification.id }, global })
      await view.find('select').setValue(locale)
      await view.find('button').trigger('click')
      await flushPromises()
      const html = view.find('iframe').attributes('srcdoc')!
      expect(html).toContain(notificationGuidance[locale])
      expect(html).not.toContain('class="button"')
      expect(html).not.toContain('href=""')
      expect(html).toContain('class="legal-link"')
      expect(html).not.toContain('https://admin.kulturbytes.de')
      expect(html).not.toContain('/findings')
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

describe('manual delivery retries', () => {
  it('links separate failure KPIs to exact delivery filters', async () => {
    const view = mount(Page, { global })
    await flushPromises()
    const links = view.findAll('a')
    expect(links.map((link) => link.attributes('to'))).toContain(
      '/notifications/deliveries?status=permanent_failure',
    )
    expect(view.text()).toContain('Temporär fehlgeschlagen')
    view.unmount()
  })
  it('lists deliveries from URL filters and applies changes', async () => {
    route.query = { status: 'permanent_failure' }
    const view = mount(DeliveryList, { global })
    await flushPromises()
    expect(api.notificationDeliveries).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'permanent_failure' }),
    )
    expect(view.text()).toContain('recipient@example.test')
    expect(view.text()).toContain('Automatischer neuer Versuch:')
    await view.findAll('select')[0]!.setValue('sent')
    await view.find('form').trigger('submit')
    await flushPromises()
    expect(api.notificationDeliveries).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: 'sent' }),
    )
    view.unmount()
  })
  it('shows the delivery empty state', async () => {
    api.notificationDeliveries.mockResolvedValue({ ...notificationDeliveryPage, items: [] })
    const view = mount(DeliveryList, { global })
    await flushPromises()
    expect(view.text()).toContain('Keine E-Mail-Versände für diese Auswahl.')
    view.unmount()
  })
  for (const status of ['failed', 'queued', 'sending', 'sent', 'cancelled'])
    it(`does not expose manual retry for ${status}`, async () => {
      api.notificationDelivery.mockResolvedValue({ ...notificationDeliveryDetail, status })
      const view = mount(Delivery, { global })
      await flushPromises()
      expect(view.findAll('button').some((button) => button.text() === 'Erneut versuchen')).toBe(
        false,
      )
      if (status === 'failed') expect(view.text()).toContain('Automatischer neuer Versuch:')
      view.unmount()
    })
  it('confirms permanent failures, blocks double clicks and navigates to the new delivery', async () => {
    api.notificationDelivery.mockResolvedValue({
      ...notificationDeliveryDetail,
      status: 'permanent_failure',
      last_error: 'smtp_553',
    })
    let resolve!: (value: { delivery_id: string }) => void
    api.retryNotificationDelivery.mockReturnValue(
      new Promise((done) => {
        resolve = done
      }),
    )
    const view = mount(Delivery, { global })
    await flushPromises()
    expect(view.text()).toContain('SMTP-Server hat den Versand dauerhaft abgelehnt.')
    await view
      .findAll('button')
      .find((button) => button.text() === 'Erneut versuchen')!
      .trigger('click')
    await flushPromises()
    const send = view
      .findAll('button')
      .find((button) => button.text() === 'Versand erneut einreihen')!
    await send.trigger('click')
    await send.trigger('click')
    expect(api.retryNotificationDelivery).toHaveBeenCalledTimes(1)
    expect(send.attributes('disabled')).toBeDefined()
    expect(send.text()).toBe('Wird eingereiht…')
    resolve({ delivery_id: '10000000-0000-4000-8000-000000000099' })
    await flushPromises()
    expect(navigate).toHaveBeenCalledWith(
      '/notifications/deliveries/10000000-0000-4000-8000-000000000099',
    )
    view.unmount()
  })
  for (const code of [
    'notification_retry_obsolete',
    'notification_retry_not_allowed',
    'notification_retry_already_queued',
  ])
    it(`maps ${code} to local error text`, async () => {
      api.notificationDelivery.mockResolvedValue({
        ...notificationDeliveryDetail,
        status: 'permanent_failure',
      })
      api.retryNotificationDelivery.mockRejectedValue(new AdminApiError(failure(409, code)))
      const view = mount(Delivery, { global })
      await flushPromises()
      await view
        .findAll('button')
        .find((button) => button.text() === 'Erneut versuchen')!
        .trigger('click')
      await flushPromises()
      await view
        .findAll('button')
        .find((button) => button.text() === 'Versand erneut einreihen')!
        .trigger('click')
      await flushPromises()
      expect(view.find('dialog [role="alert"]').text()).toBe(failure(409, code).message)
      view.unmount()
    })
  it('shows successor and predecessor links and hides retry on an older chain member', async () => {
    api.notificationDelivery.mockResolvedValue({
      ...notificationDeliveryDetail,
      status: 'permanent_failure',
      retry_of_delivery_id: notification.id,
      retries: [notificationDeliveryDetail],
    })
    const view = mount(Delivery, { global })
    await flushPromises()
    expect(view.text()).toContain('Vorheriger Versand')
    expect(view.text()).toContain('Weiterer Versuch:')
    expect(view.findAll('button').some((button) => button.text() === 'Erneut versuchen')).toBe(
      false,
    )
    view.unmount()
  })
  it('uses typed bodyless POST and rejects unsafe proxy methods or overrides', async () => {
    const response = {
      delivery_id: notification.id,
      retry_of_delivery_id: notificationDeliveryDetail.id,
      status: 'queued',
    }
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(response)))
    await createAdminApi(fetcher).retryNotificationDelivery(notificationDeliveryDetail.id)
    expect(fetcher).toHaveBeenCalledWith(
      expect.stringContaining('/retry'),
      expect.objectContaining({
        method: 'POST',
        body: undefined,
        headers: { 'X-Admin-CSRF': '1' },
      }),
    )
    const input = {
      path: `/api/v1/notification-deliveries/${notificationDeliveryDetail.id}/retry`,
      method: 'POST',
      query: new URLSearchParams(),
      authorization: 'Bearer token',
      origin: 'http://admin.test',
      csrf: '1',
    }
    const upstream = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(response), { status: 201 }))
    expect((await forwardAdminRequest(input, 'http://backend', upstream)).status).toBe(201)
    expect(upstream.mock.calls[0]![1].headers).toMatchObject({
      Origin: 'http://admin.test',
      'X-Admin-CSRF': '1',
    })
    for (const method of ['GET', 'PATCH', 'DELETE'])
      expect((await forwardAdminRequest({ ...input, method }, 'http://backend')).status).toBe(405)
    for (const body of [{ recipient: 'other@example.test' }, {}, null])
      expect((await forwardAdminRequest({ ...input, body }, 'http://backend')).status).toBe(422)
    expect(
      (
        await forwardAdminRequest(
          { ...input, path: input.path.replace('/retry', '/send') },
          'http://backend',
        )
      ).status,
    ).toBe(404)
    expect(
      (await forwardAdminRequest({ ...input, authorization: undefined }, 'http://backend')).status,
    ).toBe(401)
  })
})
