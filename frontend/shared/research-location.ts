import { z } from './zod'
import { analyticalQueryPlanSchema, analyticalEnvelopeSchema } from './research-analytics'
const slot = z
  .string()
  .min(1)
  .max(160)
  .refine((text) => !!text.trim() && text.isWellFormed())
const latitude = z.number().finite().min(-90).max(90)
const longitude = z.number().finite().min(-180).max(180)
export const locationContextSchema = z
  .object({
    latitude: latitude.nullable().optional(),
    longitude: longitude.nullable().optional(),
    display_name: slot.nullable().optional(),
    source: z.enum(['browser_geolocation', 'nominatim_reverse', 'manual']),
  })
  .strict()
  .refine(
    (v) =>
      (v.latitude != null) === (v.longitude != null) &&
      (v.latitude != null || v.display_name != null),
  )
export type LocationContext = z.infer<typeof locationContextSchema>
const addressField = z.string().max(300).nullable().optional()
export const placeSchema = z
  .object({
    display_name: z.string().min(1).max(2000).nullable().optional(),
    latitude: latitude.nullable().optional(),
    longitude: longitude.nullable().optional(),
    osm_type: z.enum(['node', 'way', 'relation']).nullable().optional(),
    osm_id: z.number().int().positive().nullable().optional(),
    place_type: z.string().max(100).nullable().optional(),
    country_code: z.string().max(3).nullable().optional(),
    address: z
      .object({
        road: addressField,
        house_number: z.string().max(100).nullable().optional(),
        city: addressField,
        municipality: addressField,
        locality: addressField,
        district: addressField,
        county: addressField,
        state: addressField,
        postcode: z.string().max(100).nullable().optional(),
        country: addressField,
      })
      .strict()
      .nullable()
      .optional(),
    bbox: z.tuple([latitude, longitude, latitude, longitude]).nullable().optional(),
  })
  .strict()
  .refine(
    (v) =>
      (v.latitude != null) === (v.longitude != null) &&
      (!v.bbox || (v.bbox[0] <= v.bbox[2] && v.bbox[1] <= v.bbox[3])),
  )
export const geographicQueryPlanSchema = analyticalQueryPlanSchema
  .safeExtend({
    place_query: slot.nullable(),
    location_relation: z.enum(['none', 'nearby']),
  })
  .superRefine((p, ctx) => {
    if (
      (p.unsupported_reason === 'outside_research' &&
        (p.place_query !== null || p.location_relation !== 'none')) ||
      (p.location_relation === 'nearby' &&
        (p.place_query !== null ||
          p.area_query !== null ||
          p.venue_query !== null ||
          p.clarification !== 'needs_location')) ||
      (p.location_relation === 'none' && p.clarification === 'needs_location')
    )
      ctx.addIssue({ code: 'custom', message: 'Inconsistent location plan' })
  })
const envelope = analyticalEnvelopeSchema.extend({
  schema_version: z.literal('research-query-plan-v6'),
  prompt_version: z.literal('research-planner-v9'),
  plan: geographicQueryPlanSchema,
  diagnostics: analyticalEnvelopeSchema.shape.diagnostics.extend({
    planner_prompt_version: z.literal('research-planner-v9'),
  }),
})
export const geographicPlanResponseSchema = z.discriminatedUnion('kind', [
  envelope.extend({ kind: z.literal('plan') }),
  envelope.extend({ kind: z.literal('needs_clarification') }),
])
