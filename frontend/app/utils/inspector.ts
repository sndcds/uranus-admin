import { entityTypeSchema, type EntitySection } from '#shared/contracts'
import { entitySections } from './entities'
import { parseMembershipKey } from './graph'

/** Local navigation only; API actions and their validated contracts remain unchanged. */
export function inspectorIdentity(type: string, key: string) {
  const parsed = entityTypeSchema.safeParse(type)
  if (!parsed.success) return null
  const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i
  const valid =
    type === 'team_membership'
      ? !!parseMembershipKey(key)
      : type === 'partner_request'
        ? key.split(':').length === 3 &&
          key.startsWith('partner-request:') &&
          key
            .split(':')
            .slice(1)
            .every((part) => uuid.test(part))
        : uuid.test(key)
  return valid ? { type: parsed.data, key } : null
}

export function inspectorHref(type: string, key: string): string | null {
  return inspectorIdentity(type, key) ? `/inspect/${type}/${encodeURIComponent(key)}` : null
}

export function inspectorSection(type: string): EntitySection | undefined {
  return (Object.keys(entitySections) as EntitySection[]).find(
    (section) => entitySections[section].type === type,
  )
}
