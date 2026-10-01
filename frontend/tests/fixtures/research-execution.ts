import type { ExecutionResult, ResearchExecutionResponse } from '../../shared/contracts'
import { researchEvent, semanticResearchEvent } from './research'

export const countQuestion = 'Wie viele Veranstaltungen gab es in Flensburg im August?'
const flensburg = { entity_type: 'area' as const, id: 'flensburg', label: 'Flensburg' }
export function executionResponse(
  kind: ExecutionResult['kind'] = 'count',
  semantic = false,
): ResearchExecutionResponse {
  const query = {
    count: countQuestion,
    aggregate: 'Wie viele Veranstaltungen gab es pro Veranstaltungsort im August?',
    comparison: 'Wo gab es mehr Veranstaltungen, Flensburg oder Kiel?',
    records: semantic
      ? 'Was ist heute Abend in Flensburg kulturell interessant?'
      : 'Welche Veranstaltungen gab es in Flensburg im August?',
    needs_clarification: 'Wie viele Veranstaltungen gab es in Neustadt im August?',
  }[kind]
  const intent = {
    count: 'count',
    aggregate: 'aggregate',
    comparison: 'compare',
    records: semantic ? 'recommend' : 'list',
    needs_clarification: 'count',
  }[kind] as ResearchExecutionResponse['plan']['plan']['intent']
  const metric = kind === 'records' ? 'none' : 'event_count'
  const targets = [flensburg, { entity_type: 'area' as const, id: 'kiel', label: 'Kiel' }]
  const result: ExecutionResult =
    kind === 'count'
      ? { kind, metric: 'event_count', value: 123 }
      : kind === 'aggregate'
        ? {
            kind,
            metric: 'event_count',
            group_by: 'venue',
            items: [{ key: 'venue-1', name: 'Kulturhaus', value: 42 }],
          }
        : kind === 'comparison'
          ? {
              kind,
              metric: 'event_count',
              items: targets.map((target, i) => ({ target, value: i ? 156 : 123 })),
            }
          : kind === 'records'
            ? {
                kind,
                items: [
                  {
                    ...(semantic ? semanticResearchEvent : researchEvent),
                    start_date: semantic ? '2026-09-30' : '2026-08-12',
                    end_date: semantic ? '2026-09-30' : '2026-08-12',
                  },
                ],
                total: null,
              }
            : {
                kind,
                reason: 'ambiguous',
                planner_state: 'none',
                field: 'area_query',
                query: 'Neustadt',
                candidates: [
                  { entity_type: 'area', id: 'neustadt-holstein', label: 'Neustadt in Holstein' },
                  { entity_type: 'area', id: 'neustadt-glewe', label: 'Neustadt-Glewe' },
                ],
              }
  return {
    query,
    plan: {
      kind: 'plan',
      schema_version: 'research-query-plan-v3',
      prompt_version: 'research-planner-v7',
      model: 'synthetic-fixture',
      reference_date: '2026-09-30',
      timezone: 'Europe/Berlin',
      diagnostics: {
        request_id: 'a'.repeat(32),
        planner_intent: intent,
        planner_model: 'synthetic-fixture',
        planner_prompt_version: 'research-planner-v7',
        planner_ms: 10,
        total_ms: 11,
      },
      plan: {
        original_query: query,
        intent,
        entity_type: 'event',
        semantic_query: semantic ? 'kulturell interessant' : null,
        area_query:
          kind === 'comparison' || kind === 'aggregate'
            ? null
            : kind === 'needs_clarification'
              ? 'Neustadt'
              : 'Flensburg',
        venue_query: null,
        organization_query: null,
        event_type_queries: [],
        category_queries: [],
        genre_queries: [],
        temporal: semantic ? 'today' : kind === 'comparison' ? 'none' : 'explicit_range',
        ordering: null,
        limit: null,
        explicit_from_date: semantic || kind === 'comparison' ? null : '2026-08-01',
        explicit_to_date: semantic || kind === 'comparison' ? null : '2026-08-31',
        time_of_day: semantic ? 'evening' : 'none',
        metric,
        group_by: kind === 'aggregate' ? 'venue' : 'none',
        comparison_targets:
          kind === 'comparison'
            ? targets.map((target) => ({ kind: 'area', query: target.label }))
            : [],
        semantic_focus: null,
        requires_semantic_relevance: semantic,
        answer_mode: kind === 'needs_clarification' ? 'count' : semantic ? 'recommendation' : kind,
        clarification: 'none',
        unsupported_reason: null,
      },
    },
    resolution:
      kind === 'comparison'
        ? targets.map((target) => ({ field: 'comparison_targets', query: target.label, target }))
        : ['aggregate', 'needs_clarification'].includes(kind)
          ? []
          : [{ field: 'area_query', query: 'Flensburg', target: flensburg }],
    result,
    execution: {
      structured: kind !== 'needs_clarification',
      semantic,
      from_date: semantic ? '2026-09-30' : kind === 'comparison' ? null : '2026-08-01',
      to_date: semantic ? '2026-09-30' : kind === 'comparison' ? null : '2026-08-31',
      time_from: semantic ? '18:00:00' : null,
      event_type_ids: [],
      category_ids: [],
      genre_keys: [],
    },
    observed_at: '2026-09-30T10:00:00Z',
    timezone: 'Europe/Berlin',
    diagnostics: {
      planner_ms: 10,
      resolution_ms: 2,
      execution_ms: 3,
      total_ms: 15,
      returned_count:
        kind === 'count' ? 1 : kind === 'comparison' ? 2 : kind === 'needs_clarification' ? 0 : 1,
    },
  }
}

export const sortedEventsQuestion =
  'welche veranstaltungen sind in flensburg? sortiere die nach datum. zeige nur 2 ergebnisse.'
export function sortedEventsResponse(
  ordering: 'asc' | 'desc' | null = 'asc',
): ResearchExecutionResponse {
  const response = executionResponse('records')
  response.query = sortedEventsQuestion
  Object.assign(response.plan.plan, {
    original_query: sortedEventsQuestion,
    ordering,
    limit: 2,
    temporal: 'none',
    explicit_from_date: null,
    explicit_to_date: null,
  })
  response.execution.from_date = null
  response.execution.to_date = null
  const items = ['2025-06-16', '2025-09-27'].map((date, i) => ({
    ...researchEvent,
    entity_key: `20000000-0000-4000-8000-00000000000${i + 1}`,
    name: `Veranstaltung ${i + 1}`,
    start_date: date,
    end_date: date,
  }))
  response.result = {
    kind: 'records',
    items: ordering === 'desc' ? items.reverse() : items,
    total: null,
  }
  response.diagnostics.returned_count = 2
  return response
}
