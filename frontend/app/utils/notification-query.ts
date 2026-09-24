import { z } from '#shared/zod'
import {
  notificationStatusSchema,
  notificationTypeSchema,
  notificationDeliveryStatusSchema,
  notificationDeliveryKindSchema,
} from '#shared/contracts'
import { AdminApiError, failure } from '#shared/errors'

const pagination = {
  organization_id: z.uuid().optional(),
  days: z.coerce.number().int().min(1).max(365).optional(),
  page: z.coerce.number().int().min(1).max(100000).default(1),
  page_size: z.coerce.number().int().min(1).max(100).optional(),
}
const notifications = z
  .object({
    ...pagination,
    status: notificationStatusSchema.optional(),
    notification_type: notificationTypeSchema.optional(),
  })
  .strict()
const deliveries = z
  .object({
    ...pagination,
    status: notificationDeliveryStatusSchema.optional(),
    delivery_kind: notificationDeliveryKindSchema.optional(),
  })
  .strict()
export function notificationQuery(query: Record<string, unknown>, delivery = false) {
  // Repeated/null query values must not silently turn into an unfiltered request.
  if (Object.values(query).some((value) => typeof value !== 'string'))
    throw new AdminApiError(failure(422))
  const parsed = (delivery ? deliveries : notifications).safeParse(query)
  if (!parsed.success) throw new AdminApiError(failure(422))
  return parsed.data
}
