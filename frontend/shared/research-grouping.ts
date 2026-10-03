import { z } from './zod'

// Browser projection of the executable v9 subset. Other wire capabilities are
// rejected before execution and never occur in ResearchExecutionResponse.plan.
const name = z
  .string()
  .min(1)
  .max(160)
  .refine((value) => !!value.trim())
const dimensions = z
  .array(
    z.enum([
      'event',
      'venue',
      'organization',
      'category',
      'genre',
      'event_type',
      'month',
      'municipality',
    ]),
  )
  .min(1)
  .max(3)
  .refine((values) => new Set(values).size === values.length)
const temporal = z
  .object({
    field: z.literal('start_date'),
    period: z.enum([
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
    from_date: z.iso.date().nullable(),
    to_date: z.iso.date().nullable(),
    time_of_day: z.enum(['none', 'morning', 'afternoon', 'evening', 'night']),
    before_time: z.null(),
    after_time: z.null(),
    weekday: z.null(),
    calendar_relation: z.literal('none'),
    calendar_area_query: z.null(),
    overlap: z.literal(false),
    multi_day: z.literal(false),
    lookback: z.null(),
    lookback_unit: z.null(),
  })
  .strict()
  .superRefine((value, ctx) => {
    if (
      value.period === 'explicit_range'
        ? !value.from_date || !value.to_date || value.from_date > value.to_date
        : value.from_date !== null || value.to_date !== null
    ) {
      ctx.addIssue({ code: 'custom', message: 'Invalid temporal bounds' })
    }
  })
const groupedPlan = z
  .object({
    original_query: z
      .string()
      .min(1)
      .max(2000)
      .refine((value) => !!value.trim() && value.isWellFormed()),
    intent: z.enum(['aggregate', 'rank']),
    entity_type: z.enum(['event', 'occurrence']),
    metric: z
      .object({
        operation: z.enum(['event_count', 'occurrence_count']),
        field: z.null(),
        distinct_by: z.null(),
        numerator: z.null(),
        denominator: z.null(),
        measure: z.null(),
        window: z.null(),
        currency: z.null(),
      })
      .strict(),
    group_by: dimensions,
    ordering: z.enum(['asc', 'desc']).nullable(),
    limit: z.number().int().min(1).max(20).nullable(),
    filters: z
      .array(
        z
          .object({
            field: z.enum(['venue', 'organization', 'category', 'event_type', 'genre']),
            operator: z.literal('eq'),
            value: name,
          })
          .strict(),
      )
      .max(16),
    metric_filter: z.null(),
    taxonomy: z.null(),
    temporal: temporal.nullable(),
    spatial: z
      .object({
        relation: z.enum(['inside', 'outside']),
        place_query: z.null(),
        area_query: name,
        radius_m: z.null(),
        reference: z.literal('named'),
      })
      .strict()
      .nullable(),
    price: z.null(),
    semantic: z.null(),
    relation: z.null(),
    trend: z.null(),
    anomaly: z.null(),
    explain: z.null(),
    knowledge: z.null(),
    comparison_targets: z.array(z.never()).max(0),
    clarification: z.literal('none'),
    unsupported_reason: z.null(),
  })
  .strict()
const ms = z.number().finite().nonnegative()
export const groupedPlanResponseSchema = z
  .object({
    kind: z.literal('plan'),
    schema_version: z.literal('research-query-plan-v9'),
    prompt_version: z.literal('research-planner-v15'),
    model: name,
    plan: groupedPlan,
    reference_date: z.iso.date(),
    timezone: z.string().max(64),
    diagnostics: z
      .object({
        request_id: z.string().regex(/^[a-f0-9]{32}$/),
        planner_intent: z.enum(['aggregate', 'rank']),
        planner_model: name,
        planner_prompt_version: z.literal('research-planner-v15'),
        planner_ms: ms,
        total_ms: ms,
      })
      .strict(),
  })
  .strict()
  .superRefine((value, ctx) => {
    if (
      value.diagnostics.planner_intent !== value.plan.intent ||
      value.diagnostics.planner_model !== value.model
    ) {
      ctx.addIssue({ code: 'custom', message: 'Inconsistent planner envelope' })
    }
  })
