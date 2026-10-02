import { expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import {
  geographicQueryPlanSchema,
  geographicPlanResponseSchema,
  locationContextSchema,
} from '../../shared/research-location'
import { executionResponse } from '../fixtures/research-execution'

it('mirrors the coordinated geographic fields and validates the complete v6 envelope', () => {
  const api = JSON.parse(readFileSync('docs/openapi.json', 'utf8'))
  const legacy = executionResponse().plan
  const plan = {
    ...legacy.plan,
    intent: 'list',
    answer_mode: 'records',
    metric: 'none',
    group_by: 'none',
    area_query: null,
    taxonomy: null,
    spatial_metric: null,
    area_relation: 'inside',
    place_query: 'Bachstraße Flensburg',
    location_relation: 'none',
  }
  expect(geographicQueryPlanSchema.parse(plan)).toEqual(plan)
  expect(Object.keys(plan).sort()).toEqual(
    api.components.schemas.GeographicQueryPlan.required.sort(),
  )
  const envelope = {
    ...legacy,
    schema_version: 'research-query-plan-v6',
    prompt_version: 'research-planner-v9',
    plan,
    diagnostics: {
      ...legacy.diagnostics,
      planner_intent: 'list',
      planner_prompt_version: 'research-planner-v9',
    },
  }
  expect(geographicPlanResponseSchema.parse(envelope)).toEqual(envelope)
  expect(
    geographicQueryPlanSchema.safeParse({ ...plan, location_relation: 'nearby' }).success,
  ).toBe(false)
  expect(
    geographicQueryPlanSchema.safeParse({
      ...plan,
      place_query: null,
      location_relation: 'nearby',
      clarification: 'needs_location',
    }).success,
  ).toBe(true)
})
it('rejects partial, nonfinite and untrusted locations', () => {
  for (const fields of [
    {},
    { latitude: 1 },
    { longitude: 1 },
    { latitude: NaN, longitude: 1 },
    { latitude: '54', longitude: 9 },
    { display_name: ' ' },
    { display_name: 'Flensburg', osm_id: 1 },
    { display_name: '\ud800' },
  ])
    expect(locationContextSchema.safeParse({ source: 'manual', ...fields }).success).toBe(false)
})
