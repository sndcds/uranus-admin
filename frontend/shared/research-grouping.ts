import { z } from './zod'

// Browser projection of the executable v9 subset. Other wire capabilities are
// rejected before execution and never occur in ResearchExecutionResponse.plan.
const name = z
  .string()
  .min(1)
  .max(160)
  .refine((value) => !!value.trim())
const topic = z
  .string()
  .min(1)
  .max(500)
  .refine((value) => !!value.trim())
const intents = z.enum(['list', 'search', 'count', 'aggregate', 'rank', 'compare', 'taxonomy'])
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
      'weekday',
      'municipality',
      'region',
      'country',
    ]),
  )
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
    weekday: z
      .enum(['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'])
      .nullable(),
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
const executablePlan = z
  .object({
    original_query: z
      .string()
      .min(1)
      .max(2000)
      .refine((value) => !!value.trim() && value.isWellFormed()),
    intent: intents,
    entity_type: z.enum(['event', 'occurrence', 'venue', 'organization', 'municipality', 'region']),
    metric: z
      .object({
        operation: z.enum([
          'event_count',
          'occurrence_count',
          'venue_count',
          'organization_count',
          'value',
          'distinct_count',
        ]),
        field: z.enum(['start_date', 'longitude', 'latitude']).nullable(),
        distinct_by: z.enum(['event', 'occurrence', 'venue', 'organization']).nullable(),
        numerator: z.null(),
        denominator: z.null(),
        measure: z.null(),
        window: z.null(),
        currency: z.null(),
      })
      .strict()
      .superRefine((metric, ctx) => {
        if (
          (metric.operation === 'value') !== (metric.field !== null) ||
          (metric.operation === 'distinct_count') !== (metric.distinct_by !== null)
        )
          ctx.addIssue({ code: 'custom', message: 'Invalid metric field' })
      })
      .nullable(),
    group_by: dimensions,
    ordering: z.enum(['asc', 'desc']).nullable(),
    limit: z.number().int().min(1).max(20).nullable(),
    filters: z
      .array(
        z.union([
          z
            .object({
              field: z.enum(['venue', 'organization', 'category', 'event_type', 'genre']),
              operator: z.literal('eq'),
              value: name,
            })
            .strict(),
          z
            .object({
              field: z.literal('start_time'),
              operator: z.literal('gte'),
              value: z.string().regex(/^([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.[0-9]{1,6})?$/),
              upper: z.null(),
            })
            .strict(),
        ]),
      )
      .max(16),
    metric_filter: z
      .object({ operator: z.literal('eq'), value: z.literal(0), upper: z.null() })
      .strict()
      .nullable(),
    taxonomy: z.enum(['genre', 'event_type', 'category']).nullable(),
    temporal: temporal.nullable(),
    spatial: z
      .union([
        z
          .object({
            relation: z.enum(['inside', 'outside']),
            place_query: z.null(),
            area_query: name,
            radius_m: z.null(),
            reference: z.literal('named'),
          })
          .strict(),
        z
          .object({
            relation: z.literal('at'),
            place_query: name,
            area_query: z.null(),
            radius_m: z.null(),
            reference: z.literal('named'),
          })
          .strict(),
        z
          .object({
            relation: z.literal('nearby'),
            place_query: z.null(),
            area_query: z.null(),
            radius_m: z.null(),
            reference: z.literal('user_location'),
          })
          .strict(),
      ])
      .nullable(),
    price: z.null(),
    semantic: z.object({ query: topic, focus: topic.nullable() }).strict().nullable(),
    relation: z.null(),
    trend: z.null(),
    anomaly: z.null(),
    explain: z.null(),
    knowledge: z.null(),
    comparison_targets: z
      .array(z.object({ kind: z.enum(['venue', 'organization', 'region']), query: name }).strict())
      .max(4),
    clarification: z.enum(['none', 'needs_criteria', 'needs_location', 'needs_date']),
    unsupported_reason: z.null(),
  })
  .strict()
const ms = z.number().finite().nonnegative()
const envelopeSchema = z
  .object({
    kind: z.enum(['plan', 'needs_clarification']),
    schema_version: z.literal('research-query-plan-v9'),
    prompt_version: z.literal('research-planner-v15'),
    model: name,
    plan: executablePlan,
    reference_date: z.iso.date(),
    timezone: z.string().max(64),
    diagnostics: z
      .object({
        request_id: z.string().regex(/^[a-f0-9]{32}$/),
        planner_intent: intents,
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
      (value.kind === 'plan') !== (value.plan.clarification === 'none') ||
      value.diagnostics.planner_intent !== value.plan.intent ||
      value.diagnostics.planner_model !== value.model
    ) {
      ctx.addIssue({ code: 'custom', message: 'Inconsistent planner envelope' })
    }
  })

const recurringSet = (maximum: number) =>
  z
    .array(z.number().int().min(1).max(maximum))
    .max(maximum)
    .refine((values) => new Set(values).size === values.length)
const calendarTemporal = temporal
  .safeExtend({
    recurring_weekdays: recurringSet(7),
    recurring_months: recurringSet(12),
  })
  .refine((value) => value.weekday === null || value.recurring_weekdays.length === 0)
export const groupedPlanResponseSchema = envelopeSchema
export const calendarPlanResponseSchema = z
  .object({
    ...envelopeSchema.shape,
    schema_version: z.literal('research-query-plan-v10'),
    prompt_version: z.literal('research-planner-v16'),
    plan: executablePlan.extend({ temporal: calendarTemporal.nullable() }),
    diagnostics: envelopeSchema.shape.diagnostics.extend({
      planner_prompt_version: z.literal('research-planner-v16'),
    }),
  })
  .strict()
  .superRefine((value, ctx) => {
    if (
      (value.kind === 'plan') !== (value.plan.clarification === 'none') ||
      value.diagnostics.planner_intent !== value.plan.intent ||
      value.diagnostics.planner_model !== value.model
    ) {
      ctx.addIssue({ code: 'custom', message: 'Inconsistent planner envelope' })
    }
  })
