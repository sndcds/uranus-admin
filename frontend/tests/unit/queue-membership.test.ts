import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import * as vue from 'vue'
import Queue from '../../app/pages/queues/[kind].vue'
import FilterBar from '../../app/components/FilterBar.vue'
import StatusBadge from '../../app/components/StatusBadge.vue'
import { membershipFixture, membershipKey } from '../fixtures/memberships'
import { membershipStatusSchema, queuePageSchema } from '../../shared/contracts'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'

const route = vue.reactive({
  params: { kind: 'team_invitations' },
  query: {} as Record<string, string>,
  fullPath: '/queues/team_invitations',
})
function navigate({ query }: { query: Record<string, string | undefined> }) {
  route.query = Object.fromEntries(
    Object.entries(query).filter((entry): entry is [string, string] => entry[1] !== undefined),
  )
  route.fullPath = `/queues/${route.params.kind}?${new URLSearchParams(route.query)}`
  return Promise.resolve()
}
const queue = vi.fn(async (_kind, query) =>
  membershipFixture(query.membership_status === 'joined' || !!query.entity_key),
)
let wrapper: ReturnType<typeof shallowMount>
function mount() {
  wrapper = shallowMount(Queue, {
    global: {
      components: { FilterBar, StatusBadge },
      stubs: {
        FilterBar: false,
        StatusBadge: false,
        DataListShell: { template: '<ul><slot /></ul>' },
      },
    },
  })
  return wrapper
}
beforeEach(() => {
  vi.clearAllMocks()
  route.params.kind = 'team_invitations'
  route.query = {}
  route.fullPath = '/queues/team_invitations'
  for (const key of ['ref', 'computed', 'watch', 'onMounted', 'onBeforeUnmount'] as const)
    vi.stubGlobal(key, vue[key])
  vi.stubGlobal('useRoute', () => route)
  vi.stubGlobal('useRouter', () => ({ push: navigate }))
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: { queue } }))
})
afterEach(() => {
  wrapper?.unmount()
  vi.unstubAllGlobals()
})
it('defaults to invited and restores membership choices from URL/history', async () => {
  const page = mount()
  await flushPromises()
  expect(page.get('select').element.value).toBe('invited')
  expect(queue).toHaveBeenLastCalledWith('team_invitations', { membership_status: 'invited' })
  for (const status of ['joined', 'all']) {
    await page.get('select').setValue(status)
    await page.get('form').trigger('submit')
    await flushPromises()
    expect(route.query.membership_status).toBe(status)
    expect(route.query.page).toBe('1')
    expect(queue.mock.lastCall?.[1].membership_status).toBe(status)
  }
  await navigate({ query: { membership_status: 'joined' } })
  await flushPromises()
  expect(page.get('select').element.value).toBe('joined')
  await navigate({ query: {} })
  await flushPromises()
  expect(page.get('select').element.value).toBe('invited')
})
it('preserves exact membership links and labels joined records correctly', async () => {
  route.query = { entity_key: membershipKey }
  const page = mount()
  await flushPromises()
  expect(page.get('select').attributes('disabled')).toBeDefined()
  expect(page.text()).toContain('Direkt aufgerufene Teammitgliedschaft')
  expect(page.getComponent(StatusBadge).text()).toBe('Beigetreten')
  expect(page.findComponent({ name: 'EmptyState' }).exists()).toBe(false)
  await page.get('form').trigger('submit')
  await flushPromises()
  expect(queue.mock.lastCall?.[1].entity_key).toBe(membershipKey)
})
it('keeps partner requests on their own status field', async () => {
  route.params.kind = 'partner_requests'
  route.query = { status: 'accepted' }
  const page = mount()
  await flushPromises()
  expect(page.find('select').exists()).toBe(false)
  expect(queue).toHaveBeenLastCalledWith('partner_requests', { status: 'accepted' })
})
it('rejects invalid membership status before fetching and validates responses', async () => {
  route.query = { membership_status: 'active' }
  mount()
  await flushPromises()
  expect(queue).not.toHaveBeenCalled()
  expect(membershipStatusSchema.safeParse('active').success).toBe(false)
  expect(queuePageSchema.parse(membershipFixture(true)).items[0]!.status).toBe('joined')
})
it('allows membership_status only for the membership proxy route', async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json(membershipFixture(true)))
  const input = {
    method: 'GET',
    authorization: 'Bearer test-only',
    path: '/api/v1/work-queues/team_invitations',
    query: new URLSearchParams({ membership_status: 'joined' }),
  }
  expect((await forwardAdminRequest(input, 'http://127.0.0.1:8000', fetcher)).status).toBe(200)
  expect(String(fetcher.mock.calls[0]![0])).toContain('membership_status=joined')
  for (const path of ['partner_requests', 'user_activation']) {
    expect(
      (
        await forwardAdminRequest(
          { ...input, path: `/api/v1/work-queues/${path}` },
          'http://127.0.0.1:8000',
          fetcher,
        )
      ).status,
    ).toBe(422)
  }
  expect(
    (
      await forwardAdminRequest(
        { ...input, query: new URLSearchParams({ status: 'joined' }) },
        'http://127.0.0.1:8000',
        fetcher,
      )
    ).status,
  ).toBe(422)
})
