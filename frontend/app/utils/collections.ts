import type { EntityPage, EntitySection } from '#shared/contracts'
import { entityFactLabel } from './entities'
import { hasOperationValue } from './operations'

export type CollectionRecord = EntityPage['items'][number]

// Inventory facts only. Context (parent venue, username) is presented separately.
const collectionFacts = {
  events: ['event_dates', 'venue_name', 'space_name'],
  organizations: ['events', 'venues', 'memberships'],
  venues: ['spaces'],
  spaces: [],
  users: ['memberships'],
  images: ['image_links', 'orphan'],
} as const satisfies Record<EntitySection, readonly (keyof CollectionRecord['facts'])[]>

export function entityCollectionFacts(section: EntitySection, item: CollectionRecord) {
  return collectionFacts[section]
    .filter((key) => hasOperationValue(item.facts[key]))
    .map((key) => ({ label: entityFactLabel(section, key), value: item.facts[key] }))
}

/** Preserve the canonical name; omit only exact repeated identity/context values. */
export function collectionContext(section: EntitySection, item: CollectionRecord): string[] {
  const values =
    section === 'users'
      ? [item.email, item.facts.username, item.organization_name]
      : section === 'spaces'
        ? [item.facts.venue_name, item.organization_name, item.address]
        : section === 'images'
          ? [item.subtitle, item.organization_name]
          : [item.organization_name, item.address]
  const seen = new Set([item.entity_name.trim()])
  return values.flatMap((value) => {
    const text = value?.trim()
    if (!text || seen.has(text)) return []
    seen.add(text)
    return [text]
  })
}
