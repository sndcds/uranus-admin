import {
  geographicPlanResponseSchema,
  locationContextSchema,
  placeSchema,
} from './research-location'
import { analyticalPlanResponseSchema } from './research-analytics'
import { z } from './zod'
import {
  genreKeySchema,
  researchRecordSchema,
  semanticResearchRecordSchema,
  researchTypeSchema,
} from './research'

const nonblank = (max: number) =>
  z
    .string()
    .min(1)
    .max(max)
    .refine((value) => !!value.trim())
export const researchQuestionSchema = nonblank(2000).refine((value) => value.isWellFormed())
export const researchPlanRequestSchema = z.object({ query: researchQuestionSchema }).strict()
export const researchQueryRequestSchema = researchPlanRequestSchema.extend({
  location_context: locationContextSchema.nullable().optional(),
})
const slot = nonblank(160)
const topic = nonblank(500)
const intent = z.enum(['search', 'list', 'count', 'aggregate', 'recommend', 'compare'])
export const executionMetricSchema = z.enum([
  'event_count',
  'occurrence_count',
  'venue_count',
  'organization_count',
])
const metric = z.enum([...executionMetricSchema.options, 'none'])
const clarification = z.enum(['none', 'needs_criteria', 'needs_location', 'needs_date'])
export const researchQueryPlanSchema = z
  .object({
    original_query: researchQuestionSchema,
    intent,
    entity_type: researchTypeSchema,
    semantic_query: topic.nullable(),
    area_query: slot.nullable(),
    venue_query: slot.nullable(),
    organization_query: slot.nullable(),
    event_type_queries: z.array(slot).max(8),
    category_queries: z.array(slot).max(8),
    genre_queries: z.array(slot).max(8),
    temporal: z.enum([
      'none',
      'today',
      'tomorrow',
      'this_weekend',
      'next_week',
      'this_month',
      'this_year',
      'past',
      'future',
      'explicit_range',
    ]),
    ordering: z.enum(['asc', 'desc']).nullable(),
    limit: z.number().int().min(1).max(20).nullable(),
    explicit_from_date: z.iso.date().nullable(),
    explicit_to_date: z.iso.date().nullable(),
    time_of_day: z.enum(['none', 'evening']),
    metric,
    group_by: z.enum(['venue', 'area', 'organization', 'category', 'none']),
    comparison_targets: z
      .array(z.object({ kind: z.enum(['venue', 'area', 'organization']), query: slot }).strict())
      .max(4),
    semantic_focus: topic.nullable(),
    requires_semantic_relevance: z.boolean(),
    answer_mode: z.enum(['records', 'count', 'aggregate', 'recommendation', 'comparison']),
    clarification,
    unsupported_reason: z
      .enum(['outside_research', 'multi_area', 'unsupported_constraint'])
      .nullable(),
  })
  .strict()
  .superRefine((plan, ctx) => {
    const fail = () => ctx.addIssue({ code: 'custom', message: 'Inconsistent research plan' })
    const modes = {
      search: 'records',
      list: 'records',
      count: 'count',
      aggregate: 'aggregate',
      recommend: 'recommendation',
      compare: 'comparison',
    }
    if (plan.answer_mode !== modes[plan.intent]) fail()
    if (plan.limit !== null && !['list', 'search', 'recommend'].includes(plan.intent)) fail()
    if (
      plan.ordering !== null &&
      (!['list', 'search'].includes(plan.intent) ||
        plan.answer_mode !== 'records' ||
        plan.entity_type !== 'event' ||
        (plan.semantic_query !== null && plan.unsupported_reason !== 'unsupported_constraint'))
    )
      fail()
    const semantic = plan.semantic_query !== null
    if (
      plan.requires_semantic_relevance !== semantic ||
      (plan.semantic_focus !== null && !semantic) ||
      (['search', 'recommend'].includes(plan.intent) && !semantic)
    )
      fail()
    if (plan.temporal === 'explicit_range') {
      if (
        !plan.explicit_from_date ||
        !plan.explicit_to_date ||
        plan.explicit_from_date > plan.explicit_to_date
      )
        fail()
    } else if (plan.explicit_from_date !== null || plan.explicit_to_date !== null) fail()
    if (plan.time_of_day === 'evening' && plan.temporal === 'none') fail()
    if (['count', 'aggregate'].includes(plan.intent) && plan.metric === 'none') fail()
    if (['search', 'list', 'recommend'].includes(plan.intent) && plan.metric !== 'none') fail()
    if ((plan.intent === 'aggregate') !== (plan.group_by !== 'none')) fail()
    const entities = {
      event_count: 'event',
      occurrence_count: 'event',
      venue_count: 'venue',
      organization_count: 'organization',
    }
    if (plan.metric !== 'none' && entities[plan.metric] !== plan.entity_type) fail()
    if (
      plan.intent !== 'compare' &&
      (plan.comparison_targets.length || plan.clarification === 'needs_criteria')
    )
      fail()
    if (
      plan.intent === 'compare' &&
      plan.clarification === 'none' &&
      !plan.unsupported_reason &&
      (plan.comparison_targets.length < 2 || plan.metric === 'none')
    )
      fail()
    const targets = plan.comparison_targets.map(
      (target) =>
        `${target.kind}:${target.query.trim().toLowerCase().replaceAll('ß', 'ss').replaceAll('ς', 'σ')}`,
    )
    if (new Set(targets).size !== targets.length) fail()
    if (
      plan.unsupported_reason === 'outside_research' &&
      (plan.intent !== 'list' ||
        plan.entity_type !== 'event' ||
        semantic ||
        plan.area_query !== null ||
        plan.venue_query !== null ||
        plan.organization_query !== null ||
        plan.event_type_queries.length ||
        plan.category_queries.length ||
        plan.genre_queries.length ||
        plan.temporal !== 'none' ||
        plan.ordering !== null ||
        plan.limit !== null ||
        plan.time_of_day !== 'none' ||
        plan.metric !== 'none' ||
        plan.group_by !== 'none' ||
        plan.comparison_targets.length ||
        plan.semantic_focus !== null ||
        plan.clarification !== 'none')
    )
      fail()
  })
const milliseconds = z.number().finite().nonnegative()
const planEnvelope = z
  .object({
    schema_version: z.literal('research-query-plan-v3'),
    prompt_version: z.literal('research-planner-v7'),
    model: z.string().min(1).max(160),
    plan: researchQueryPlanSchema,
    reference_date: z.iso.date(),
    timezone: z.string().max(64),
    diagnostics: z
      .object({
        request_id: z.string().regex(/^[a-f0-9]{32}$/),
        planner_intent: intent,
        planner_model: z.string().min(1).max(160),
        planner_prompt_version: z.literal('research-planner-v7'),
        planner_ms: milliseconds,
        total_ms: milliseconds,
      })
      .strict(),
  })
  .strict()
export const researchPlanResponseSchema = z.discriminatedUnion('kind', [
  planEnvelope.extend({ kind: z.literal('plan') }),
  planEnvelope.extend({ kind: z.literal('needs_clarification') }),
])
export const resolutionCandidateSchema = z
  .object({
    entity_type: z.enum([
      'area',
      'venue',
      'organization',
      'category',
      'event_type',
      'genre',
      'place',
    ]),
    id: z.string(),
    label: z.string(),
    place: placeSchema.nullable().optional(),
  })
  .strict()
const resolutionField = z.enum([
  'place_query',
  'location_context',
  'area_query',
  'venue_query',
  'organization_query',
  'event_type_queries',
  'category_queries',
  'genre_queries',
  'comparison_targets',
])
export const resolvedFieldSchema = z
  .object({ field: resolutionField, query: slot, target: resolutionCandidateSchema })
  .strict()
const value = z.number().int().nonnegative()
export const executionResultSchema = z.discriminatedUnion('kind', [
  z
    .object({
      kind: z.literal('taxonomy'),
      taxonomy: z.enum(['genre', 'event_type', 'category']),
      total: value,
      items: z
        .array(z.object({ key: z.string(), name: z.string(), event_count: value }).strict())
        .max(20),
    })
    .strict(),
  z
    .object({
      kind: z.literal('spatial'),
      spatial_metric: z.enum(['longitude', 'latitude']),
      ordering: z.enum(['asc', 'desc']),
      items: z.array(researchRecordSchema).max(20),
    })
    .strict(),
  z.object({ kind: z.literal('count'), metric: executionMetricSchema, value }).strict(),
  z
    .object({
      kind: z.literal('aggregate'),
      metric: executionMetricSchema,
      group_by: z.enum([
        'event',
        'venue',
        'organization',
        'category',
        'genre',
        'event_type',
        'municipality',
        'district',
        'state',
        'country',
        'region',
      ]),
      items: z.array(z.object({ key: z.string(), name: z.string(), value }).strict()).max(20),
    })
    .strict(),
  z
    .object({
      kind: z.literal('comparison'),
      metric: executionMetricSchema,
      items: z
        .array(z.object({ target: resolutionCandidateSchema, value }).strict())
        .min(2)
        .max(4),
    })
    .strict(),
  z
    .object({
      kind: z.literal('records'),
      items: z.array(z.union([semanticResearchRecordSchema, researchRecordSchema])).max(20),
      total: value.nullable(),
    })
    .strict(),
  z
    .object({
      kind: z.literal('needs_clarification'),
      reason: z.enum(['planner', 'ambiguous', 'no_match', 'duplicate_target', 'taxonomy_conflict']),
      planner_state: clarification,
      field: resolutionField.nullable(),
      query: slot.nullable(),
      candidates: z.array(resolutionCandidateSchema).max(5),
    })
    .strict(),
])
export const executionProvenanceSchema = z
  .object({
    structured: z.boolean(),
    semantic: z.boolean(),
    from_date: z.iso.date().nullable(),
    to_date: z.iso.date().nullable(),
    time_from: z.iso.time().nullable(),
    time_of_day: z.enum(['none', 'morning', 'afternoon', 'evening', 'night']).optional(),
    area_relation: z.enum(['inside', 'outside']).optional(),
    event_type_ids: z.array(z.number().int()).max(8),
    category_ids: z.array(z.number().int()).max(8),
    genre_keys: z.array(genreKeySchema).max(8),
  })
  .strict()
export const executionDiagnosticsSchema = z
  .object({
    planner_ms: milliseconds,
    resolution_ms: milliseconds,
    execution_ms: milliseconds,
    total_ms: milliseconds,
    returned_count: value.max(20),
  })
  .strict()
export const researchExecutionResponseSchema = z
  .object({
    query: researchQuestionSchema,
    plan: z.union([
      geographicPlanResponseSchema,
      researchPlanResponseSchema,
      analyticalPlanResponseSchema,
    ]),
    resolution: z.array(resolvedFieldSchema).max(32),
    result: executionResultSchema,
    execution: executionProvenanceSchema,
    observed_at: z.iso.datetime({ offset: true }),
    timezone: z.string(),
    diagnostics: executionDiagnosticsSchema,
  })
  .strict()
export type ResearchExecutionResponse = z.infer<typeof researchExecutionResponseSchema>
export type ExecutionResult = z.infer<typeof executionResultSchema>
export type ExecutionProvenance = z.infer<typeof executionProvenanceSchema>
export type ExecutionDiagnostics = z.infer<typeof executionDiagnosticsSchema>
export type ResolutionCandidate = z.infer<typeof resolutionCandidateSchema>
export type ResolvedField = z.infer<typeof resolvedFieldSchema>
export type ResearchQueryPlan = z.infer<typeof researchQueryPlanSchema>
