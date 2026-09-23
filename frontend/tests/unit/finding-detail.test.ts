import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import FindingDetail from '../../app/components/FindingDetail.vue'
import { workflowFindings } from '../fixtures/operations-workflows'
import { AdminApiError, failure } from '../../shared/errors'

const api = { review: vi.fn() }
const item = workflowFindings.items[2]!
const views: ReturnType<typeof mount>[] = []
beforeEach(() => {
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
  vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function () {
    this.open = true
  })
  vi.spyOn(HTMLDialogElement.prototype, 'close').mockImplementation(function () {
    this.open = false
  })
  api.review.mockReset().mockResolvedValue({ ...item, status: 'in_progress' })
})
afterEach(() => {
  views.splice(0).forEach((view) => view.unmount())
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})
function setup() {
  const view = mount(FindingDetail, {
    global: {
      stubs: {
        AppIcon: true,
        ActivityThumbnail: true,
        EntityTypeBadge: true,
        SeverityBadge: true,
        StatusBadge: true,
        RecordSection: {
          props: ['title'],
          template: '<section><h3>{{ title }}</h3><slot /></section>',
        },
        CompactFacts: true,
        AssignmentEditor: true,
        TechnicalInfoBar: true,
        GraphLink: true,
        RecordMarkLink: true,
        NuxtLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
      },
    },
  })
  views.push(view)
  return view
}
async function open(
  view: ReturnType<typeof setup>,
  mode: 'live' | 'persisted' = 'persisted',
  value = item,
) {
  view.vm.open(value, mode)
  await flushPromises()
}
describe('Finding workflow boundaries', () => {
  it('uses mode, not first_seen, to distinguish saved and live findings', async () => {
    const view = setup()
    await open(view, 'persisted', { ...item, first_seen_at: null })
    expect(view.find('form').exists()).toBe(true)
    expect(view.find('assignment-editor-stub').exists()).toBe(true)
    await open(view, 'live')
    expect(view.find('form').exists()).toBe(false)
    expect(view.find('assignment-editor-stub').exists()).toBe(false)
    expect(view.text()).toContain('Live-Diagnose ohne gespeicherten Review')
    expect(api.review).not.toHaveBeenCalled()
  })
  it('never offers manual review or assignment for resolved findings', async () => {
    const view = setup()
    await open(view, 'persisted', { ...item, status: 'resolved' })
    expect(view.find('form').exists()).toBe(false)
    expect(view.find('assignment-editor-stub').exists()).toBe(false)
  })
  it('keeps an existing snooze instant exactly and clears conditional fields for open', async () => {
    const view = setup()
    const until = '2099-10-25T01:30:45Z'
    await open(view, 'persisted', { ...item, status: 'snoozed', snoozed_until: until })
    await view.get('form').trigger('submit')
    await flushPromises()
    expect(api.review).toHaveBeenLastCalledWith(
      expect.objectContaining({ snoozed_until: until, exception_reason: null }),
    )
    await view.get('select').setValue('open')
    await view.get('form').trigger('submit')
    await flushPromises()
    expect(api.review).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: 'open', snoozed_until: null, exception_reason: null }),
    )
  })
  it('rejects empty exceptions and invalid local times without a request', async () => {
    const view = setup()
    await open(view)
    await view.get('select').setValue('exception')
    await view.get('form').trigger('submit')
    expect(view.get('[role="alert"]').text()).toContain('Ausnahme begründen')
    await view.get('select').setValue('snoozed')
    await view.get('input[type="datetime-local"]').setValue('2099-03-29T02:30')
    await view.get('form').trigger('submit')
    expect(view.get('[role="alert"]').text()).toContain('gültigen zukünftigen Zeitpunkt')
    expect(api.review).not.toHaveBeenCalled()
  })
  it('retains source enrichments after review and refreshes only when closed', async () => {
    const view = setup()
    await open(view)
    await view.get('form').trigger('submit')
    await flushPromises()
    expect(view.get('[role="status"]').text()).toBe('Review gespeichert.')
    expect(view.emitted('refresh')).toBeUndefined()
    expect(view.text()).toContain('Standortvorschlag prüfen')
    expect(view.findAll('button').some((button) => button.text() === 'SQL Editor')).toBe(true)
    await view.get('[aria-label="Befund schließen"]').trigger('click')
    expect(view.emitted('refresh')).toHaveLength(1)
  })
  it('does not reload protected data while the workflow is being unmounted', async () => {
    const view = setup()
    await open(view)
    await view.get('form').trigger('submit')
    await flushPromises()
    view.unmount()
    expect(view.emitted('refresh')).toBeUndefined()
  })
  it('shows safe failure feedback and ignores a save completed after closing', async () => {
    const view = setup()
    api.review.mockRejectedValueOnce(new AdminApiError(failure(403, 'permission_denied')))
    await open(view)
    await view.get('form').trigger('submit')
    await flushPromises()
    expect(view.find('[role="alert"]').exists()).toBe(true)
    let resolve!: (value: typeof item) => void
    api.review.mockReturnValueOnce(
      new Promise<typeof item>((yes) => {
        resolve = yes
      }),
    )
    await view.get('form').trigger('submit')
    await view.get('[aria-label="Befund schließen"]').trigger('click')
    await open(view, 'persisted', { ...item, id: 'other', entity_name: 'Anderer Befund' })
    resolve({ ...item, status: 'exception' })
    await flushPromises()
    expect(view.get('h2').text()).toBe('Anderer Befund')
    expect(view.get('[role="status"]').text()).toBe('')
    expect(view.emitted('refresh')).toBeUndefined()
  })
})
