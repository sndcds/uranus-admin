import { z } from './zod'

export const suggestionFiltersSchema = z.strictObject({
  q: z.string().trim().min(2).max(120),
  limit: z.coerce.number().int().min(1).max(8).optional(),
  language: z
    .string()
    .regex(/^[a-z]{2,3}$/)
    .optional(),
})
const shownSuggestionSchema = z.strictObject({
  id: z.uuid(),
  position: z.number().int().min(1).max(8),
})
export const suggestionsSchema = z.strictObject({
  request_id: z.uuid(),
  suggestions: z.array(shownSuggestionSchema.extend({ query: z.string().max(300) })).max(8),
})
export const suggestionImpressionSchema = z
  .strictObject({
    request_id: z.uuid(),
    prefix: z.string().min(2).max(120),
    suggestions: z.array(shownSuggestionSchema).min(1).max(8),
  })
  .refine(
    (value) =>
      new Set(value.suggestions.map((s) => s.id)).size === value.suggestions.length &&
      new Set(value.suggestions.map((s) => s.position)).size === value.suggestions.length,
  )
export const suggestionSelectionSchema = z.strictObject({
  request_id: z.uuid(),
  suggestion_id: z.uuid(),
  position: z.number().int().min(1).max(8),
})
export const suggestionTelemetrySchema = z.strictObject({
  ok: z.boolean(),
  receipt: z.uuid().nullable(),
})
export type ResearchSuggestions = z.infer<typeof suggestionsSchema>
export type SuggestionImpression = z.infer<typeof suggestionImpressionSchema>
export type SuggestionSelection = z.infer<typeof suggestionSelectionSchema>
