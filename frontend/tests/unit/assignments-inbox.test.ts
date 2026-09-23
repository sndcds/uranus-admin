import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AssignmentEditor from '../../app/components/AssignmentEditor.vue'
import InlineAlert from '../../app/components/InlineAlert.vue'
import { berlinDate, berlinDueAt } from '../../app/utils/admin-time'
import {
  assignmentCreateSchema,
  assignmentLookupSchema,
  assignmentSchema,
  assignmentUpdateSchema,
  inboxPageSchema,
} from '../../shared/contracts'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'
import { createAdminApi } from '../../app/utils/admin-api'
import { unassignedFindingInboxFixture } from '../fixtures/inbox'

const adminId = '00000000-0000-4000-8000-000000000800'
const findingId = 'finding:one'
const assignment = {
  id: '00000000-0000-4000-8000-000000000810',
  finding_id: findingId,
  workflow_type: null,
  workflow_key: null,
  entity_type: 'event',
  entity_key: '00000000-0000-4000-8000-000000000030',
  assigned_to: { id: adminId, login: 'operator' },
  assigned_by_subject: `admin:${adminId}`,
  status: 'open',
  snoozed_until: null,
  due_at: '2026-10-25T22:59:59Z',
  created_at: '2026-09-22T10:00:00Z',
  updated_at: '2026-09-22T10:00:00Z',
  completed_at: null,
  version: 1,
} as const

const api = {
  admins: vi.fn(),
  assignmentForFinding: vi.fn(),
  assignmentForWorkflow: vi.fn(),
  createAssignment: vi.fn(),
  updateAssignment: vi.fn(),
}

beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
  api.admins.mockResolvedValue({ items: [assignment.assigned_to], admin_timezone: 'Europe/Berlin' })
  api.assignmentForFinding.mockResolvedValue(null)
  api.assignmentForWorkflow.mockResolvedValue(null)
  api.createAssignment.mockResolvedValue(assignment)
  api.updateAssignment.mockResolvedValue({ ...assignment, version: 2, status: 'in_progress' })
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
})
afterEach(() => vi.unstubAllGlobals())

describe('assignment and inbox contracts', () => {
  it('loads unassigned event-date findings without an entity action through the API client', async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json(unassignedFindingInboxFixture))
    const client = createAdminApi(fetcher)
    await expect(
      client.inbox({ scope: 'all', attention: 'all', page: 1, page_size: 25 }),
    ).resolves.toEqual(unassignedFindingInboxFixture)
  })

  it('keeps administrator identity separate and rejects forged workflow state', () => {
    expect(assignmentSchema.parse(assignment).assigned_to.login).toBe('operator')
    expect(
      assignmentCreateSchema.safeParse({
        finding_id: findingId,
        assigned_to_admin_id: adminId,
      }).success,
    ).toBe(true)
    for (const value of [
      { assigned_to_admin_id: adminId },
      { finding_id: findingId, workflow_type: 'geocode_request', assigned_to_admin_id: adminId },
      { finding_id: findingId, assigned_to_admin_id: adminId, assigned_by_subject: 'forged' },
    ])
      expect(assignmentCreateSchema.safeParse(value).success).toBe(false)
    expect(
      assignmentUpdateSchema.safeParse({
        version: 0,
        assigned_to_admin_id: adminId,
        status: 'done',
        due_at: null,
      }).success,
    ).toBe(false)
    expect(assignmentLookupSchema.safeParse({ finding_id: findingId }).success).toBe(true)
    expect(
      assignmentLookupSchema.safeParse({
        workflow_type: 'geocode_request',
        workflow_key: '00000000-0000-4000-8000-000000000850',
      }).success,
    ).toBe(true)
    for (const value of [
      {},
      { workflow_type: 'geocode_request' },
      { finding_id: findingId, workflow_key: 'forged' },
    ])
      expect(assignmentLookupSchema.safeParse(value).success).toBe(false)
  })

  it('uses Berlin calendar dates across the DST transition', () => {
    expect(berlinDueAt('2026-10-25')).toBe('2026-10-25T22:59:59.000Z')
    expect(berlinDate('2026-10-25T22:59:59Z')).toBe('2026-10-25')
  })

  it('renders admin choices and creates a finding assignment', async () => {
    const view = mount(AssignmentEditor, { props: { findingId } })
    await flushPromises()
    expect(view.text()).toContain('operator')
    expect(view.text()).not.toContain('User-UUID')
    await view.get('input[type="date"]').setValue('2026-10-25')
    await view.get('form').trigger('submit')
    await flushPromises()
    expect(api.createAssignment).toHaveBeenCalledWith({
      finding_id: findingId,
      assigned_to_admin_id: adminId,
      status: 'open',
      due_at: '2026-10-25T22:59:59.000Z',
    })
    expect(view.text()).toContain('Zuständigkeit gespeichert')
  })

  it('loads and creates an assignment for the durable geocoding task', async () => {
    const workflowKey = '00000000-0000-4000-8000-000000000850'
    const entityKey = '00000000-0000-4000-8000-000000000020'
    const view = mount(AssignmentEditor, {
      props: { workflowType: 'geocode_request', workflowKey, entityType: 'venue', entityKey },
    })
    await flushPromises()
    expect(api.assignmentForWorkflow).toHaveBeenCalledWith('geocode_request', workflowKey)
    await view.get('form').trigger('submit')
    await flushPromises()
    expect(api.createAssignment).toHaveBeenCalledWith({
      workflow_type: 'geocode_request',
      workflow_key: workflowKey,
      entity_type: 'venue',
      entity_key: entityKey,
      assigned_to_admin_id: adminId,
      status: 'open',
      due_at: null,
    })
  })

  it('shows the unassigned workflow form using nullable API responses and admin options', async () => {
    const fetcher = vi
      .fn()
      .mockImplementation(async (path: string) =>
        Response.json(
          path.endsWith('/admins')
            ? { items: [assignment.assigned_to], admin_timezone: 'Europe/Berlin' }
            : null,
        ),
      )
    vi.stubGlobal('useNuxtApp', () => ({ $adminApi: createAdminApi(fetcher) }))
    const view = mount(AssignmentEditor, {
      props: {
        workflowType: 'geocode_request',
        workflowKey: '00000000-0000-4000-8000-000000000850',
        entityType: 'venue',
        entityKey: assignment.entity_key,
      },
      global: { components: { InlineAlert }, stubs: { SectionHeader: true } },
    })
    await flushPromises()
    expect(view.find('[role="alert"]').exists()).toBe(false)
    expect(view.text()).not.toContain('Zuständigkeit konnte nicht geladen werden.')
    expect(view.get('form').isVisible()).toBe(true)
    expect(view.get('select option').text()).toBe('operator')
    expect(view.get('select').element.value).toBe(adminId)
    expect(view.get('form button').text()).toBe('Aufgabe zuweisen')
    view.unmount()
  })

  it('validates safe inbox links and excludes unexpected fields', () => {
    const page = {
      items: [
        {
          id: `assignment:${assignment.id}`,
          kind: 'assignment',
          title: 'Event 30',
          summary: 'Beschreibung fehlt',
          entity_type: 'event',
          entity_key: assignment.entity_key,
          entity_name: 'Sommerkonzert',
          organization_name: 'Kulturverein',
          entity_action: {
            type: 'view',
            route: 'activity',
            entity_type: 'event',
            entity_key: assignment.entity_key,
            href: `/events/${assignment.entity_key}`,
          },
          severity: 'error',
          status: 'open',
          workflow_status: null,
          candidate_count: null,
          occurred_at: assignment.updated_at,
          snoozed_until: null,
          due_at: assignment.due_at,
          finding_snoozed_until: null,
          is_overdue: false,
          due_today: true,
          assignment,
          href: `/findings?entity_key=${assignment.entity_key}&rule=missing_description`,
        },
      ],
      counts: { critical: 1, mine: 1, unassigned: 0, due_today: 1, overdue: 0, snoozed: 0 },
      pagination: { page: 1, page_size: 25, total: 1, pages: 1 },
      admin_timezone: 'Europe/Berlin',
      observed_at: '2026-10-25T10:00:00Z',
    }
    expect(inboxPageSchema.safeParse(page).success).toBe(true)
    for (const href of [
      '/inbox',
      'https://evil.invalid',
      '/findings?entity_key=x&rule=x&token=secret',
    ])
      expect(
        inboxPageSchema.safeParse({
          ...page,
          items: [{ ...page.items[0], href }],
        }).success,
      ).toBe(false)
    expect(
      inboxPageSchema.safeParse({
        ...page,
        items: [{ ...page.items[0], recipient: 'secret@example.invalid' }],
      }).success,
    ).toBe(false)
  })
})

describe('assignment proxy boundary', () => {
  const baseInput = {
    path: '/api/v1/assignments',
    method: 'POST',
    body: { finding_id: findingId, assigned_to_admin_id: adminId },
    authorization: 'Bearer fixture-token',
    query: new URLSearchParams(),
  }
  it('forwards only bounded authenticated assignment writes', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{}', { status: 201 }))
    expect((await forwardAdminRequest(baseInput, 'http://127.0.0.1:8000', fetcher)).status).toBe(
      201,
    )
    expect(JSON.parse(fetcher.mock.calls[0]?.[1].body)).toEqual({
      finding_id: findingId,
      assigned_to_admin_id: adminId,
      status: 'open',
    })
    fetcher.mockClear()
    for (const change of [
      { authorization: undefined },
      { method: 'DELETE' },
      { path: '/api/v1/assignments/not-a-uuid', method: 'PATCH' },
      { body: { ...baseInput.body, assigned_by_subject: 'forged' } },
      { query: new URLSearchParams('finding_id=unexpected') },
    ]) {
      const result = await forwardAdminRequest(
        { ...baseInput, ...change },
        'http://127.0.0.1:8000',
        fetcher,
      )
      expect(result.status).toBeGreaterThanOrEqual(400)
    }
    expect(fetcher).not.toHaveBeenCalled()
  })

  it('forwards only one complete bounded assignment lookup identity', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('null', { status: 200 }))
    const input = {
      path: '/api/v1/assignments',
      method: 'GET',
      authorization: 'Bearer fixture-token',
      query: new URLSearchParams({ finding_id: findingId }),
    }
    expect((await forwardAdminRequest(input, 'http://127.0.0.1:8000', fetcher)).status).toBe(200)
    for (const query of [
      '',
      'workflow_type=geocode_request',
      `finding_id=${encodeURIComponent(findingId)}&workflow_key=forged`,
      'workflow_type=unknown&workflow_key=task',
    ])
      expect(
        (
          await forwardAdminRequest(
            { ...input, query: new URLSearchParams(query) },
            'http://127.0.0.1:8000',
            fetcher,
          )
        ).status,
      ).toBe(422)
  })
})
