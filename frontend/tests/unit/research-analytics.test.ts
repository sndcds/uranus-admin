import { readFileSync } from 'node:fs'
import { computed } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { analyticalQueryPlanSchema } from '../../shared/research-analytics'
import { researchExecutionResponseSchema } from '../../shared/research-execution'
import ResearchQueryAnswer from '../../app/components/ResearchQueryAnswer.vue'
import { executionResponse } from '../fixtures/research-execution'
import { researchEvent } from '../fixtures/research'

const cases: { query: string; plan: unknown }[] = JSON.parse(
  readFileSync('../backend/tests/fixtures/research_analytics.json', 'utf8'),
)
afterEach(() => vi.unstubAllGlobals())

it.each(cases)('validates the full Planner/Admin plan: $query', ({ plan }) => {
  expect(analyticalQueryPlanSchema.parse(plan)).toEqual(plan)
  expect(
    analyticalQueryPlanSchema.safeParse({ ...(plan as object), sql: 'SELECT 1' }).success,
  ).toBe(false)
})

function response(index: number, result: unknown) {
  const base = executionResponse()
  const plan = analyticalQueryPlanSchema.parse(cases[index]!.plan)
  return researchExecutionResponseSchema.parse({
    ...base,
    query: plan.original_query,
    plan: {
      ...base.plan,
      schema_version: 'research-query-plan-v5',
      prompt_version: 'research-planner-v8',
      plan,
      diagnostics: {
        ...base.plan.diagnostics,
        planner_intent: plan.intent,
        planner_prompt_version: 'research-planner-v8',
      },
    },
    result,
  })
}

it('renders exact taxonomy text and counts without event cards; makes truncation visible', () => {
  vi.stubGlobal('computed', computed)
  const wrapper = mount(ResearchQueryAnswer, {
    props: {
      response: response(0, {
        kind: 'taxonomy',
        taxonomy: 'genre',
        total: 21,
        items: [{ key: '1:2', name: 'Jazz', event_count: 123 }],
      }),
    },
    global: { stubs: { ResearchResult: true, EmptyState: true } },
  })
  expect(wrapper.text()).toContain('21 verwendete Genres')
  expect(wrapper.text()).toContain('1 angezeigt')
  expect(wrapper.text()).toContain('Jazz – 123 Veranstaltungen')
  expect(wrapper.text()).toContain('Exakte strukturierte Auswertung')
  expect(wrapper.find('research-result-stub').exists()).toBe(false)
})

it('renders a spatial summary before its event card', () => {
  vi.stubGlobal('computed', computed)
  const index = cases.findIndex((c) => c.query.includes('geographisch'))
  const wrapper = mount(ResearchQueryAnswer, {
    props: {
      response: response(index, {
        kind: 'spatial',
        spatial_metric: 'longitude',
        ordering: 'asc',
        items: [{ ...researchEvent, location: { latitude: 54, longitude: 8 } }],
      }),
    },
    global: { stubs: { ResearchResult: true, EmptyState: true } },
  })
  expect(wrapper.text()).toContain('Westlichster Treffer:')
  expect(wrapper.text()).toContain('8° Länge')
  expect(wrapper.text()).not.toContain('Sortierung: Datum')
  expect(wrapper.find('research-result-stub').exists()).toBe(true)
})

it('labels genre rankings as genres, not categories', () => {
  vi.stubGlobal('computed', computed)
  const index = cases.findIndex((c) => c.query === 'Zeige die häufigsten Genres')
  const wrapper = mount(ResearchQueryAnswer, {
    props: {
      response: response(index, {
        kind: 'aggregate',
        metric: 'event_count',
        group_by: 'genre',
        items: [{ key: '1:2', name: 'Jazz', value: 123 }],
      }),
    },
    global: { stubs: { EmptyState: true } },
  })
  expect(wrapper.text()).toContain('Veranstaltungen nach Genre')
  expect(wrapper.find('table').text()).toContain('Jazz')
})
