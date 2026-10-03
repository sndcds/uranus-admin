import { z } from './zod'

const name = z.string().min(1).max(160)
const set = (max: number) =>
  z
    .array(z.number().int().min(1).max(max))
    .max(max)
    .refine((v) => new Set(v).size === v.length)
const temporal = z
  .object({
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
    weekdays: set(7),
    months: set(12),
  })
  .strict()
  .refine((v) =>
    v.period === 'explicit_range'
      ? v.from_date !== null && v.to_date !== null && v.from_date <= v.to_date
      : v.from_date === null && v.to_date === null,
  )
export const legacyResearchPlanSummarySchema = z
  .object({
    intent: z.enum([
      'list',
      'search',
      'recommend',
      'count',
      'aggregate',
      'rank',
      'taxonomy',
      'spatial_rank',
    ]),
    entity_type: z.enum(['event', 'venue', 'organization']),
    metric: z.enum([
      'none',
      'event_count',
      'occurrence_count',
      'venue_count',
      'organization_count',
    ]),
    groupings: z
      .array(
        z.enum([
          'event',
          'venue',
          'organization',
          'category',
          'event_type',
          'genre',
          'month',
          'weekday',
          'municipality',
          'district',
          'state',
          'country',
          'region',
        ]),
      )
      .max(3)
      .refine((v) => new Set(v).size === v.length),
    ordering: z.enum(['asc', 'desc']).nullable(),
    limit: z.number().int().min(1).max(20).nullable(),
    temporal,
    filters: z
      .object({
        venue: name.nullable(),
        organization: name.nullable(),
        event_types: z.array(name).max(8),
        categories: z.array(name).max(8),
        genres: z.array(name).max(8),
      })
      .strict(),
    areas: z.array(z.object({ name, relation: z.enum(['inside', 'outside']) }).strict()).max(1),
    semantic_query: name.nullable(),
    semantic_focus: name.nullable(),
    taxonomy: z.enum(['genre', 'event_type', 'category']).nullable(),
    spatial_metric: z.enum(['longitude', 'latitude']).nullable(),
  })
  .strict()
  .refine((v) => new TextEncoder().encode(JSON.stringify(v)).length <= 2048)
const legacyResearchConversationContextSchema = z
  .object({ previous_turns: z.array(legacyResearchPlanSummarySchema).min(1).max(4) })
  .strict()
  .refine((v) => new TextEncoder().encode(JSON.stringify(v)).length <= 8192)
export const researchPlanSummaryV12Schema = legacyResearchPlanSummarySchema.safeExtend({
  areas: z
    .array(
      z
        .object({
          name,
          relation: z.enum(['inside', 'outside']),
          expected_level: z
            .enum(['municipality', 'district', 'state', 'country', 'region'])
            .nullable(),
        })
        .strict(),
    )
    .max(4),
})
export const researchConversationContextV12Schema = z
  .object({
    previous_turns: z.array(researchPlanSummaryV12Schema).min(1).max(4),
  })
  .strict()
  .refine((v) => new TextEncoder().encode(JSON.stringify(v)).length <= 8192)
export const researchPlanSummarySchema = z.union([
  researchPlanSummaryV12Schema,
  legacyResearchPlanSummarySchema,
])
export const researchConversationContextSchema = z.union([
  researchConversationContextV12Schema,
  legacyResearchConversationContextSchema,
])
export type ResearchPlanSummary = z.infer<typeof researchPlanSummarySchema>
export type ResearchConversationContext = z.infer<typeof researchConversationContextSchema>
