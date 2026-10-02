import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { computed } from 'vue'
import { readFileSync } from 'node:fs'
import {
  researchExecutionResponseSchema,
  researchPlanRequestSchema,
  executionResultSchema,
} from '../../shared/contracts'
import { createAdminApi } from '../../app/utils/admin-api'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'
import {
  researchAnswerMode,
  researchAnswerQuery,
  researchAnswerUrl,
} from '../../app/utils/research-answer'
import { researchQuery } from '../../app/utils/research'
import { failure } from '../../shared/errors'
import ResearchQueryAnswer from '../../app/components/ResearchQueryAnswer.vue'
import ResearchResult from '../../app/components/ResearchResult.vue'
import ResearchSemanticExplanation from '../../app/components/ResearchSemanticExplanation.vue'
import { researchEvent } from '../fixtures/research'
import {
  countQuestion,
  executionResponse,
  sortedEventsResponse,
} from '../fixtures/research-execution'

afterEach(() => vi.unstubAllGlobals())
const variants = ['count', 'aggregate', 'comparison', 'records', 'needs_clarification'] as const
it.each(variants)('validates closed %s responses', (kind) => {
  const response = executionResponse(kind)
  expect(researchExecutionResponseSchema.parse(response)).toEqual(response)
  for (const field of [
    'query',
    'plan',
    'resolution',
    'result',
    'execution',
    'observed_at',
    'timezone',
    'diagnostics',
  ]) {
    const missing = Object.fromEntries(Object.entries(response).filter(([key]) => key !== field))
    expect(researchExecutionResponseSchema.safeParse(missing).success).toBe(false)
  }
  for (const key of ['result', 'execution', 'diagnostics', 'plan'] as const)
    expect(
      researchExecutionResponseSchema.safeParse({
        ...response,
        [key]: { ...response[key], secret: 'hidden' },
      }).success,
    ).toBe(false)
})
it('mirrors OpenAPI result discriminator and required plan fields', () => {
  const api = JSON.parse(readFileSync('docs/openapi.json', 'utf8'))
  const response = api.components.schemas.ResearchExecutionResponse
  expect(Object.keys(response.properties.result.discriminator.mapping).sort()).toEqual(
    [...variants, 'taxonomy', 'spatial'].sort(),
  )
  expect(Object.keys(executionResponse().plan.plan).sort()).toEqual(
    api.components.schemas.ResearchQueryPlan.required.sort(),
  )
  expect(
    api.paths['/api/v1/research/query'].post.responses['200'].content['application/json'].schema
      .$ref,
  ).toBe('#/components/schemas/ResearchExecutionResponse')
})
it('enforces bounded values, records, resolution, genres, date/time and consistent plans', () => {
  const r = executionResponse()
  const invalid = [
    { result: { kind: 'count', metric: 'event_count', value: -1 } },
    { result: { kind: 'count', metric: 'event_count', value: '123' } },
    { result: { kind: 'count', metric: 'unknown', value: 123 } },
    {
      result: {
        kind: 'records',
        items: Array(21).fill(researchEvent),
        total: null,
      },
    },
    { resolution: Array(33).fill(r.resolution[0]) },
    { execution: { ...r.execution, category_ids: Array(9).fill(1) } },
    { execution: { ...r.execution, genre_keys: ['1:0'] } },
    { execution: { ...r.execution, from_date: '2026-02-30' } },
    { execution: { ...r.execution, time_from: '28:00:00' } },
    { diagnostics: { ...r.diagnostics, total_ms: Infinity } },
    { diagnostics: { ...r.diagnostics, returned_count: 21 } },
  ]
  for (const update of invalid)
    expect(researchExecutionResponseSchema.safeParse({ ...r, ...update }).success).toBe(false)
  for (const change of [
    { metric: 'none' },
    { answer_mode: 'records' },
    { requires_semantic_relevance: true },
    { explicit_to_date: '2026-07-01' },
    { group_by: 'venue' },
    { unsupported_reason: 'outside_research' },
  ])
    expect(
      researchExecutionResponseSchema.safeParse({
        ...r,
        plan: { ...r.plan, plan: { ...r.plan.plan, ...change } },
      }).success,
    ).toBe(false)
  expect(
    executionResultSchema.safeParse({ kind: 'comparison', metric: 'event_count', items: [] })
      .success,
  ).toBe(false)
  const clarification = executionResponse('needs_clarification').result
  if (clarification.kind === 'needs_clarification')
    expect(
      executionResultSchema.safeParse({
        ...clarification,
        candidates: Array(6).fill(clarification.candidates[0]),
      }).success,
    ).toBe(false)
  expect(
    researchExecutionResponseSchema.safeParse(executionResponse('records', true)).success,
  ).toBe(true)
})
it.each(['', ' ', 'x'.repeat(2001), '\ud800'])('rejects invalid questions', (query) => {
  expect(researchPlanRequestSchema.safeParse({ query }).success).toBe(false)
})
it('round-trips dedicated question URLs without changing classic or semantic URLs', () => {
  const query = Object.fromEntries(new URLSearchParams(researchAnswerUrl(countQuestion)))
  expect(researchAnswerMode(query)).toBe(true)
  expect(researchAnswerQuery(query)).toEqual({ success: true, data: countQuestion })
  expect(researchAnswerMode({})).toBe(false)
  expect(researchAnswerMode({ q: countQuestion, search_mode: 'semantic' })).toBe(false)
  expect(researchQuery({ q: 'Kultur', search_mode: 'semantic' }).success).toBe(true)
  expect(researchAnswerQuery({ question: ['one', 'two'] }).success).toBe(false)
  expect(researchAnswerQuery({ question: 'x'.repeat(2001) }).success).toBe(false)
})
it('POSTs only the validated question with CSRF, a 60s timeout and cancellation', async () => {
  const timeout = vi.spyOn(AbortSignal, 'timeout')
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(executionResponse())))
  const api = createAdminApi(fetcher)
  const controller = new AbortController()
  expect(await api.researchQuery(countQuestion, controller.signal)).toEqual(executionResponse())
  expect(fetcher.mock.calls[0]![0]).toBe('/api/admin/api/v1/research/query')
  const options = fetcher.mock.calls[0]![1]
  expect(options).toMatchObject({
    method: 'POST',
    body: JSON.stringify({ query: countQuestion }),
    headers: { 'X-Admin-CSRF': '1' },
    cache: 'no-store',
  })
  expect(timeout).toHaveBeenCalledWith(60000)
  controller.abort()
  expect(options.signal.aborted).toBe(true)
  expect(api.viewRead('/api/v1/research/query')).toBeUndefined()
  fetcher.mockResolvedValue(new Response('{}'))
  await expect(api.researchQuery(countQuestion)).rejects.toThrow()
  expect(() => api.researchQuery(' ')).toThrow()
  timeout.mockRestore()
})
const proxyInput = {
  path: '/api/v1/research/query',
  method: 'POST',
  query: new URLSearchParams(),
  body: { query: countQuestion },
  sessionCookie: `admin_session=${'a'.repeat(43)}`,
  origin: 'https://admin.invalid',
  csrf: '1',
}
it('proxy forwards the exact query route, body and auth headers with a bounded timeout', async () => {
  const timeout = vi.spyOn(AbortSignal, 'timeout')
  const fetcher = vi.fn().mockResolvedValue(new Response('{}'))
  expect((await forwardAdminRequest(proxyInput, 'http://backend.invalid', fetcher)).status).toBe(
    200,
  )
  expect(fetcher.mock.calls[0]![1]).toMatchObject({
    method: 'POST',
    redirect: 'error',
    body: JSON.stringify(proxyInput.body),
    headers: { Cookie: proxyInput.sessionCookie, Origin: proxyInput.origin, 'X-Admin-CSRF': '1' },
  })
  expect(timeout).toHaveBeenCalledWith(58000)
  timeout.mockRestore()
})
it.each([
  [{ method: 'GET' }, 405],
  [{ method: 'PATCH' }, 405],
  [{ path: '/api/v1/research/plan' }, 404],
  [{ body: { query: countQuestion, plan: {} } }, 422],
  [{ body: { query: ' ' } }, 422],
  [{ body: { query: 'x'.repeat(2001) } }, 422],
  [{ query: new URLSearchParams('q=a&q=b') }, 422],
  [{ sessionCookie: undefined }, 401],
])('proxy rejects unapproved query inputs %j', async (change, status) => {
  const fetcher = vi.fn()
  expect(
    (await forwardAdminRequest({ ...proxyInput, ...change }, 'http://backend.invalid', fetcher))
      .status,
  ).toBe(status)
  expect(fetcher).not.toHaveBeenCalled()
})
it.each([
  'research_planner_unavailable',
  'research_execution_unavailable',
  'research_plan_unsupported',
  'research_execution_unsupported',
])('maps safe %s errors without upstream prose', async (code) => {
  const status = code.endsWith('unavailable') ? 503 : 422
  const fetcher = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ error: { code, message: 'provider-secret' } }), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  const result = await forwardAdminRequest(proxyInput, 'http://backend.invalid', fetcher)
  expect(result.status).toBe(status)
  expect(result.body).toEqual({ error: { code, message: failure(status, code).message } })
})
function render(kind: (typeof variants)[number], semantic = false) {
  vi.stubGlobal('computed', computed)
  return mount(ResearchQueryAnswer, {
    props: { response: executionResponse(kind, semantic) },
    global: {
      components: { ResearchResult, ResearchSemanticExplanation },
      stubs: {
        NuxtLink: { template: '<a><slot /></a>' },
        ResearchBadges: true,
        AppIcon: true,
        EmptyState: true,
      },
    },
  })
}
describe('deterministic answers', () => {
  it.each([false, true])(
    'renders a clear empty record selection (semantic=%s)',
    async (semantic) => {
      const view = render('records', semantic)
      const response = executionResponse('records', semantic)
      if (response.result.kind !== 'records') throw new Error('Expected records fixture')
      response.result.items = []
      response.result.total = semantic ? null : 0
      await view.setProps({ response })
      expect(view.get('empty-state-stub').attributes('message')).toBe(
        semantic
          ? 'Keine ausreichend passenden Veranstaltungen gefunden.'
          : 'Keine passenden Datensätze gefunden.',
      )
      expect(view.findAllComponents(ResearchResult)).toHaveLength(0)
      expect(view.text()).not.toMatch(/Schwelle|Prozent|0\.10/)
      view.unmount()
    },
  )
  it('shows exact count and only resolved context, including zero and all metrics', async () => {
    const view = render('count')
    expect(view.get('[data-testid=research-count]').text()).toBe('123 Veranstaltungen')
    expect(view.text()).toContain('Flensburg · 01.08.2026 – 31.08.2026')
    expect(view.text()).toContain('Exakte strukturierte Auswertung')
    expect(view.get('details').attributes('open')).toBeUndefined()
    expect(view.text()).toContain('Europe/Berlin')
    expect(view.text()).not.toContain('synthetic-fixture')
    for (const [metric, label] of [
      ['event_count', 'Veranstaltungen'],
      ['occurrence_count', 'Termine'],
      ['venue_count', 'Veranstaltungsorte'],
      ['organization_count', 'Organisationen'],
    ] as const) {
      await view.setProps({
        response: {
          ...executionResponse(),
          resolution: [],
          result: { kind: 'count', metric, value: 0 },
        },
      })
      expect(view.get('[data-testid=research-count]').text()).toBe(`0 ${label}`)
      expect(view.text()).not.toContain('Flensburg')
    }
    view.unmount()
  })
  it.each(['aggregate', 'comparison'] as const)(
    'renders %s labels and exact values without ranking claims',
    (kind) => {
      const view = render(kind)
      expect(view.get('table').text()).toContain(kind === 'aggregate' ? 'Kulturhaus' : 'Kiel')
      expect(view.get('table').text()).toContain(kind === 'aggregate' ? '42' : '156')
      expect(view.text()).not.toMatch(/Gewinner|besser/)
      view.unmount()
    },
  )
  it('uses exact total only when supplied and displays semantic evidence separately', async () => {
    const structured = render('records')
    expect(structured.text()).toContain('1 Ergebnisse angezeigt')
    expect(structured.text()).not.toContain('Ergebnisse insgesamt')
    const exact = executionResponse('records')
    exact.plan.plan.entity_type = 'venue'
    if (exact.result.kind !== 'records') throw new Error('fixture')
    exact.result.total = 123
    await structured.setProps({ response: exact })
    expect(structured.text()).toContain('123 Ergebnisse insgesamt · 1 angezeigt')
    expect(structured.text()).not.toContain('Sortierung: Datum')
    expect(structured.text()).not.toContain('Warum passt das?')
    const semantic = render('records', true)
    expect(semantic.text()).toContain('Semantische Relevanzsuche · bis zu 20 Treffer')
    expect(semantic.text()).toContain('Keine vollständige Zählung')
    expect(semantic.text()).toContain('Warum passt das?')
    expect(semantic.text()).not.toMatch(
      /Ergebnisse insgesamt|Es gibt|Exakte strukturierte Auswertung/,
    )
    structured.unmount()
    semantic.unmount()
  })
  it('offers clarification candidates as editable text and escapes labels', async () => {
    const view = render('needs_clarification')
    expect(view.text()).toContain('Frage präzisieren')
    await view.get('button').trigger('click')
    expect(view.emitted('adjust')?.[0]).toEqual(['Neustadt in Holstein'])
    for (const [planner_state, text] of [
      ['needs_date', 'Welchen Zeitraum'],
      ['needs_location', 'Welchen Ort'],
      ['needs_criteria', 'Welche Vergleichskriterien'],
    ] as const) {
      const response = executionResponse('needs_clarification')
      if (response.result.kind === 'needs_clarification')
        response.result.planner_state = planner_state
      await view.setProps({ response })
      expect(view.text()).toContain(text)
    }
    view.unmount()
  })
})

it.each([null, 'asc', 'desc'] as const)(
  'renders effective %s order, limit and full dates',
  async (ordering) => {
    const response = sortedEventsResponse(ordering)
    expect(researchExecutionResponseSchema.parse(response)).toEqual(response)
    const view = render('records')
    await view.setProps({ response })
    expect(view.text()).toContain(
      `Sortierung: Datum ${ordering === 'desc' ? 'absteigend' : 'aufsteigend'}`,
    )
    expect(view.text()).toContain('Maximal 2 Ergebnisse')
    expect(view.findAll('article')).toHaveLength(2)
    expect(view.text()).toContain('16.06.2025')
    expect(view.text()).toContain('27.09.2025')
    expect(view.text()).not.toMatch(
      /Semantische Relevanzsuche|Ergebnisse insgesamt|Keine vollständige Zählung/,
    )
    view.unmount()
  },
)
it.each([null, 'asc', 'desc'] as const)(
  'accepts %s direction without a requested limit',
  (ordering) => {
    const response = executionResponse('records')
    response.plan.plan.ordering = ordering
    expect(researchExecutionResponseSchema.parse(response)).toEqual(response)
  },
)
it('shows default ASC without implying a requested limit and keeps semantic ranking separate', () => {
  const view = render('records')
  expect(view.text()).toContain('Sortierung: Datum aufsteigend')
  expect(view.text()).not.toContain('Maximal')
  const semantic = render('records', true)
  expect(semantic.text()).not.toContain('Sortierung: Datum')
  expect(semantic.text()).toContain('30.09.2026')
  view.unmount()
  semantic.unmount()
})
it.each([
  { ordering: 'earliest' },
  { ordering: 'latest' },
  { ordering: 'none' },
  { ordering: 'best' },
  ...[0, 21, true, '1', 1.5].map((limit) => ({ limit })),
  { ordering: 'asc', entity_type: 'venue' },
  { ordering: 'desc', entity_type: 'organization' },
  { ordering: 'asc', intent: 'count', answer_mode: 'count', metric: 'event_count' },
  { limit: 2, intent: 'count', answer_mode: 'count', metric: 'event_count' },
  {
    limit: 2,
    intent: 'aggregate',
    answer_mode: 'aggregate',
    metric: 'event_count',
    group_by: 'venue',
  },
  { limit: 2, intent: 'compare', answer_mode: 'comparison', clarification: 'needs_criteria' },
  { ordering: 'asc', semantic_query: 'interesting', requires_semantic_relevance: true },
])('rejects invalid ordering/limit plans %j', (change) => {
  const response = executionResponse('records')
  expect(
    researchExecutionResponseSchema.safeParse({
      ...response,
      plan: { ...response.plan, plan: { ...response.plan.plan, ...change } },
    }).success,
  ).toBe(false)
})
it.each(['ordering', 'limit'])('requires chronological field %s even when unused', (field) => {
  const response = executionResponse('records')
  const plan = Object.fromEntries(
    Object.entries(response.plan.plan).filter(([key]) => key !== field),
  )
  expect(
    researchExecutionResponseSchema.safeParse({ ...response, plan: { ...response.plan, plan } })
      .success,
  ).toBe(false)
})
it.each([{ ordering: 'asc' }, { limit: 1 }])(
  'proxy rejects browser chronological fields %j',
  async (extra) => {
    const fetcher = vi.fn()
    const result = await forwardAdminRequest(
      { ...proxyInput, body: { query: countQuestion, ...extra } },
      'http://backend.invalid',
      fetcher,
    )
    expect(result.status).toBe(422)
    expect(fetcher).not.toHaveBeenCalled()
  },
)

it('requires distinct event type slots and preserves taxonomy conflicts', async () => {
  const r = executionResponse('records')
  r.plan.plan.event_type_queries = ['Konzerte']
  r.plan.plan.genre_queries = ['Jazz']
  r.execution.event_type_ids = [1]
  r.execution.genre_keys = ['1:2']
  expect(researchExecutionResponseSchema.parse(r).plan.plan.category_queries).toEqual([])
  const missing = structuredClone(r)
  Reflect.deleteProperty(missing.plan.plan, 'event_type_queries')
  expect(researchExecutionResponseSchema.safeParse(missing).success).toBe(false)
  r.plan.plan.event_type_queries = Array(9).fill('Konzerte')
  expect(researchExecutionResponseSchema.safeParse(r).success).toBe(false)
  r.plan.plan.event_type_queries = ['Konzerte']
  r.result = {
    kind: 'needs_clarification',
    reason: 'taxonomy_conflict',
    planner_state: 'none',
    field: 'genre_queries',
    query: 'Jazz',
    candidates: [],
  }
  expect(researchExecutionResponseSchema.parse(r).result.kind).toBe('needs_clarification')
  const view = render('records')
  await view.setProps({ response: r })
  expect(view.text()).toContain('Das Genre gehört nicht zum gewählten Veranstaltungstyp')
})

it('POSTs location only in the body and proxy rejects extra location capabilities', async () => {
  const location_context = {
    latitude: 54.79,
    longitude: 9.43,
    source: 'browser_geolocation' as const,
  }
  const fetcher = vi.fn().mockResolvedValue(Response.json(executionResponse()))
  const api = createAdminApi(fetcher)
  await api.researchQuery('Was ist hier los?', undefined, undefined, location_context)
  expect(fetcher.mock.calls[0]![0]).toBe('/api/admin/api/v1/research/query')
  expect(JSON.parse(fetcher.mock.calls[0]![1].body)).toEqual({
    query: 'Was ist hier los?',
    location_context,
  })
  const upstream = vi.fn().mockResolvedValue(Response.json({}))
  const body = { query: 'Was ist hier los?', location_context }
  expect(
    (await forwardAdminRequest({ ...proxyInput, body }, 'http://backend.invalid', upstream)).status,
  ).toBe(200)
  expect(JSON.parse(upstream.mock.calls[0]![1].body)).toEqual(body)
  for (const change of [
    { osm_id: 1 },
    { url: 'http://evil.invalid' },
    { source: 'evil' },
    { latitude: 91 },
    { longitude: null },
  ]) {
    upstream.mockClear()
    expect(
      (
        await forwardAdminRequest(
          {
            ...proxyInput,
            body: { ...body, location_context: { ...location_context, ...change } },
          },
          'http://backend.invalid',
          upstream,
        )
      ).status,
    ).toBe(422)
    expect(upstream).not.toHaveBeenCalled()
  }
})
