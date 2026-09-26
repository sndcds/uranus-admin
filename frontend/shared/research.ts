import { z } from './zod'

export const researchTypeSchema = z.enum(['event', 'venue', 'organization'])
export const researchStatusSchema = z.enum(['released', 'cancelled', 'deferred', 'rescheduled'])
const categorySchema = z.object({ id: z.number().int(), name: z.string() }).strict()
const locationSchema = z
  .object({ latitude: z.number().min(-90).max(90), longitude: z.number().min(-180).max(180) })
  .strict()
const paginationSchema = z.object({
  page: z.number().int(),
  page_size: z.number().int(),
  total: z.number().int(),
  pages: z.number().int(),
})
const linkSchema = z
  .string()
  .url()
  .refine((value) => {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password
  })
  .nullable()
export const researchRecordSchema = z
  .object({
    entity_type: researchTypeSchema,
    entity_key: z.uuid(),
    name: z.string(),
    description: z.string().nullable(),
    status: researchStatusSchema.nullable(),
    categories: z.array(categorySchema),
    language: z.string().nullable(),
    start_date: z.iso.date().nullable(),
    start_time: z.string().nullable(),
    end_date: z.iso.date().nullable(),
    end_time: z.string().nullable(),
    all_day: z.boolean().nullable(),
    organization_id: z.uuid().nullable(),
    organization_name: z.string().nullable(),
    venue_id: z.uuid().nullable(),
    venue_name: z.string().nullable(),
    space_id: z.uuid().nullable(),
    space_name: z.string().nullable(),
    city: z.string().nullable(),
    address: z.string().nullable(),
    location: locationSchema.nullable(),
    event_count: z.number().int().nonnegative().nullable(),
    source_url: linkSchema,
    image_url: linkSchema,
    created_at: z.iso.datetime({ offset: true }).nullable(),
    modified_at: z.iso.datetime({ offset: true }).nullable(),
  })
  .strict()
export const researchPageSchema = z
  .object({
    items: z.array(researchRecordSchema).max(100),
    pagination: paginationSchema,
    observed_at: z.iso.datetime({ offset: true }),
    timezone: z.string(),
  })
  .strict()
export const researchDateSchema = z
  .object({
    id: z.uuid(),
    start_date: z.iso.date(),
    start_time: z.string().nullable(),
    end_date: z.iso.date().nullable(),
    end_time: z.string().nullable(),
    all_day: z.boolean().nullable(),
    status: researchStatusSchema,
    venue_id: z.uuid().nullable(),
    venue_name: z.string().nullable(),
    space_id: z.uuid().nullable(),
    space_name: z.string().nullable(),
    city: z.string().nullable(),
    address: z.string().nullable(),
    location: locationSchema.nullable(),
  })
  .strict()
export const researchDetailSchema = z
  .object({
    item: researchRecordSchema,
    events: researchPageSchema,
    dates: z
      .object({ items: z.array(researchDateSchema).max(100), pagination: paginationSchema })
      .strict(),
    usage: z
      .array(
        z
          .object({
            kind: z.enum(['venue', 'organization', 'category']),
            key: z.string(),
            name: z.string(),
            event_count: z.number().int().nonnegative(),
          })
          .strict(),
      )
      .max(30),
    months: z
      .array(
        z.object({ month: z.iso.date(), event_count: z.number().int().nonnegative() }).strict(),
      )
      .max(120),
    observed_at: z.iso.datetime({ offset: true }),
  })
  .strict()
export const researchOptionsSchema = z
  .object({ categories: z.array(categorySchema).max(1000) })
  .strict()
export const researchExportSchema = z
  .object({
    columns: z.array(z.string()),
    rows: z.array(z.record(z.string(), z.string().nullable())).max(10000),
    total: z.number().int().nonnegative(),
    observed_at: z.iso.datetime({ offset: true }),
  })
  .strict()
export const researchQuerySchema = z
  .object({
    q: z.string().max(120).optional(),
    entity_type: z.enum(['all', 'event', 'venue', 'organization']).optional(),
    from_date: z.iso.date().optional(),
    to_date: z.iso.date().optional(),
    city: z.string().max(100).optional(),
    category: z.coerce.number().int().min(0).max(2147483647).optional(),
    status: researchStatusSchema.optional(),
    organization_id: z.uuid().optional(),
    venue_id: z.uuid().optional(),
    sort: z.enum(['date', 'name']).optional(),
    page: z.coerce.number().int().min(1).max(100000).optional(),
    page_size: z.coerce.number().int().min(1).max(100).optional(),
  })
  .strict()
  .refine((q) => !q.from_date || !q.to_date || q.from_date <= q.to_date, 'Ungültiger Zeitraum')
export type ResearchType = z.infer<typeof researchTypeSchema>
export type ResearchRecord = z.infer<typeof researchRecordSchema>
export type ResearchPage = z.infer<typeof researchPageSchema>
export type ResearchDetail = z.infer<typeof researchDetailSchema>
export type ResearchQuery = z.infer<typeof researchQuerySchema>
