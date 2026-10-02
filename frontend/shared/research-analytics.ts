import { z } from './zod'
import { researchTypeSchema } from './research'

const nonblank = (max: number) =>
  z
    .string()
    .min(1)
    .max(max)
    .refine((value) => !!value.trim())
export const researchQuestionSchema = nonblank(2000).refine((value) => value.isWellFormed())
export const researchPlanRequestSchema = z.object({ query: researchQuestionSchema }).strict()
const slot = nonblank(160)
const topic = nonblank(500)
const intent = z.enum([
  'search',
  'list',
  'count',
  'aggregate',
  'recommend',
  'compare',
  'taxonomy',
  'spatial_rank',
])
export const executionMetricSchema = z.enum([
  'event_count',
  'occurrence_count',
  'venue_count',
  'organization_count',
])
const metric = z.enum([...executionMetricSchema.options, 'none'])
const clarification = z.enum(['none', 'needs_criteria', 'needs_location', 'needs_date'])
export const analyticalQueryPlanSchema = z
  .object({
    taxonomy: z.enum(['genre', 'event_type', 'category']).nullable(),
    spatial_metric: z.enum(['longitude', 'latitude']).nullable(),
    area_relation: z.enum(['inside', 'outside']),
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
    time_of_day: z.enum(['none', 'morning', 'afternoon', 'evening', 'night']),
    metric,
    group_by: z.enum([
      'event',
      'venue',
      'area',
      'organization',
      'category',
      'genre',
      'event_type',
      'none',
    ]),
    comparison_targets: z
      .array(z.object({ kind: z.enum(['venue', 'area', 'organization']), query: slot }).strict())
      .max(4),
    semantic_focus: topic.nullable(),
    requires_semantic_relevance: z.boolean(),
    answer_mode: z.enum([
      'records',
      'count',
      'aggregate',
      'recommendation',
      'comparison',
      'taxonomy',
    ]),
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
      taxonomy: 'taxonomy',
      spatial_rank: 'records',
    }
    if (plan.answer_mode !== modes[plan.intent]) fail()
    if (
      plan.limit !== null &&
      !['list', 'search', 'recommend', 'taxonomy', 'aggregate', 'spatial_rank'].includes(
        plan.intent,
      )
    )
      fail()
    if (
      plan.ordering !== null &&
      !['taxonomy', 'aggregate', 'spatial_rank'].includes(plan.intent) &&
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
    if (['count', 'aggregate'].includes(plan.intent) && plan.metric === 'none') fail()
    if (
      ['search', 'list', 'recommend', 'taxonomy', 'spatial_rank'].includes(plan.intent) &&
      plan.metric !== 'none'
    )
      fail()
    if ((plan.intent === 'aggregate') !== (plan.group_by !== 'none')) fail()
    if (plan.group_by === 'event' && plan.metric !== 'occurrence_count') fail()
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
    if ((plan.intent === 'taxonomy') !== (plan.taxonomy !== null)) fail()
    if (plan.intent === 'taxonomy' && plan.entity_type !== 'event') fail()
    if ((plan.intent === 'spatial_rank') !== (plan.spatial_metric !== null)) fail()
    if (
      plan.intent === 'spatial_rank' &&
      (!['event', 'venue'].includes(plan.entity_type) || plan.ordering === null)
    )
      fail()
    if (plan.area_relation === 'outside' && plan.area_query === null) fail()
    if (
      semantic &&
      ['count', 'aggregate', 'compare', 'taxonomy', 'spatial_rank'].includes(plan.intent) &&
      plan.unsupported_reason === null
    )
      fail()
    const targets = plan.comparison_targets.map(
      (target) =>
        `${target.kind}:${target.query.trim().toLowerCase().replaceAll('ß', 'ss').replaceAll('ς', 'σ')}`,
    )
    if (new Set(targets).size !== targets.length) fail()
    if (
      plan.unsupported_reason === 'outside_research' &&
      (plan.taxonomy !== null ||
        plan.spatial_metric !== null ||
        plan.area_relation !== 'inside' ||
        plan.intent !== 'list' ||
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
export const analyticalEnvelopeSchema = z
  .object({
    schema_version: z.literal('research-query-plan-v5'),
    prompt_version: z.literal('research-planner-v10'),
    model: z.string().min(1).max(160),
    plan: analyticalQueryPlanSchema,
    reference_date: z.iso.date(),
    timezone: z.string().max(64),
    diagnostics: z
      .object({
        request_id: z.string().regex(/^[a-f0-9]{32}$/),
        planner_intent: intent,
        planner_model: z.string().min(1).max(160),
        planner_prompt_version: z.literal('research-planner-v10'),
        planner_ms: milliseconds,
        total_ms: milliseconds,
      })
      .strict(),
  })
  .strict()
export const analyticalPlanResponseSchema = z.discriminatedUnion('kind', [
  analyticalEnvelopeSchema.extend({ kind: z.literal('plan') }),
  analyticalEnvelopeSchema.extend({ kind: z.literal('needs_clarification') }),
])
