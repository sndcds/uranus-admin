import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import AssignmentSnooze from '../../app/components/AssignmentSnooze.vue'
import InlineAlert from '../../app/components/InlineAlert.vue'
import { adminLocalInstant, snoozePreset } from '../../app/utils/admin-time'
import { assignmentUpdateSchema } from '../../shared/contracts'
import { AdminApiError, failure } from '../../shared/errors'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'
import { inboxFixture } from '../fixtures/inbox'

const assignment = inboxFixture.items[0]!.assignment!
const updateAssignment = vi.fn()
function view(until: string | null = null) {
  return mount(AssignmentSnooze, {
    props: { assignment: { ...assignment, snoozed_until: until }, timezone: 'Europe/Berlin' },
    global: { components: { InlineAlert }, stubs: { AppIcon: true } },
  })
}
beforeEach(() => {
  vi.setSystemTime(new Date('2026-03-28T23:30:00Z')) // already March 29 in Berlin
  updateAssignment.mockReset()
  updateAssignment.mockImplementation(async (_id, body) => ({ ...assignment, ...body, version: 2 }))
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: { updateAssignment } }))
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('admin calendar snooze', () => {
  it.each([
    ['2026-03-28T12:00:00Z', 1, '2026-03-29T07:00:00.000Z'],
    ['2026-10-24T12:00:00Z', 1, '2026-10-25T08:00:00.000Z'],
    ['2026-03-28T23:30:00Z', 3, '2026-04-01T07:00:00.000Z'],
    ['2026-12-28T12:00:00Z', 7, '2027-01-04T08:00:00.000Z'],
  ] as const)('uses calendar days across DST/year boundaries %s', (now, days, expected) => {
    expect(snoozePreset(days, new Date(now), 'Europe/Berlin')).toBe(expected)
  })
  it('uses the configured timezone rather than browser timezone', () => {
    expect(snoozePreset(1, new Date('2026-03-28T23:30:00Z'), 'America/New_York')).toBe(
      '2026-03-29T13:00:00.000Z',
    )
  })
  it('rejects impossible local times and resolves repeated minutes explicitly', () => {
    expect(adminLocalInstant('2026-03-29T02:30', 'Europe/Berlin')).toBeNull()
    expect(adminLocalInstant('2026-02-30T09:00', 'Europe/Berlin')).toBeNull()
    expect(adminLocalInstant('2026-10-25T02:30', 'Europe/Berlin')).toBe('2026-10-25T00:30:00.000Z')
  })
})

describe('shared snooze controls', () => {
  it.each([
    ['Morgen', '2026-03-30T07:00:00.000Z'],
    ['In 3 Tagen', '2026-04-01T07:00:00.000Z'],
    ['Nächste Woche', '2026-04-05T07:00:00.000Z'],
  ])('saves %s as a versioned partial patch', async (label, expected) => {
    const wrapper = view()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.get('dialog').attributes('open')).toBeDefined()
    const button = wrapper.findAll('button').find((item) => item.text() === label)!
    expect(button.classes()).toContain('min-h-11')
    await button.trigger('click')
    await flushPromises()
    expect(updateAssignment).toHaveBeenCalledExactlyOnceWith(assignment.id, {
      version: 1,
      snoozed_until: expected,
    })
    expect(wrapper.emitted('updated')).toHaveLength(1)
    expect(wrapper.get('dialog').attributes('open')).toBeUndefined()
    wrapper.unmount()
  })
  it('validates custom time and saves local input in UTC', async () => {
    const wrapper = view()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    await wrapper.get('input').setValue('2026-03-29T02:30')
    await wrapper.get('form').trigger('submit')
    expect(updateAssignment).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('existiert nicht')
    await wrapper.get('input').setValue('2026-04-01T16:15')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(updateAssignment).toHaveBeenCalledWith(assignment.id, {
      version: 1,
      snoozed_until: '2026-04-01T14:15:00.000Z',
    })
    wrapper.unmount()
  })
  it('shows the absolute reminder and unsnoozes without changing status', async () => {
    const wrapper = view('2026-04-01T07:00:00Z')
    expect(wrapper.text()).toContain('01.04.2026, 09:00')
    expect(wrapper.get('time').attributes('datetime')).toBe('2026-04-01T07:00:00Z')
    await wrapper
      .findAll('button')
      .find((item) => item.text() === 'Wiedervorlage aufheben')!
      .trigger('click')
    await flushPromises()
    expect(updateAssignment).toHaveBeenCalledWith(assignment.id, {
      version: 1,
      snoozed_until: null,
    })
    wrapper.unmount()
  })
  it('does not silently retry a version conflict', async () => {
    updateAssignment.mockRejectedValue(new AdminApiError(failure(409, 'assignment_conflict')))
    const wrapper = view()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((item) => item.text() === 'Morgen')!
      .trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('zwischenzeitlich geändert')
    expect(
      wrapper
        .findAll('button')
        .find((item) => item.text() === 'Morgen')!
        .attributes('disabled'),
    ).toBeDefined()
    expect(updateAssignment).toHaveBeenCalledTimes(1)
    await wrapper
      .findAll('button')
      .find((item) => item.text() === 'Neu laden')!
      .trigger('click')
    expect(wrapper.emitted('reload')).toHaveLength(1)
    wrapper.unmount()
  })
})

it('validates and proxies only a bounded aware partial assignment patch', async () => {
  for (const value of [
    { version: 1 },
    { version: 1, status: null },
    { version: 1, snoozed_until: '2026-09-25T09:00:00' },
  ])
    expect(assignmentUpdateSchema.safeParse(value).success).toBe(false)
  const body = { version: 1, snoozed_until: '2026-09-25T07:00:00Z' }
  const fetcher = vi.fn().mockResolvedValue(Response.json({ ...assignment, ...body }))
  const result = await forwardAdminRequest(
    {
      path: `/api/v1/assignments/${assignment.id}`,
      method: 'PATCH',
      body,
      authorization: 'Bearer fixture-token',
      query: new URLSearchParams(),
    },
    'http://127.0.0.1:8000',
    fetcher,
  )
  expect(result.status).toBe(200)
  expect(JSON.parse(fetcher.mock.calls[0]![1].body)).toEqual(body)
})
