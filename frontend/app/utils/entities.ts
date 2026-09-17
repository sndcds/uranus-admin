import type { EntitySection } from '#shared/contracts'
export const entitySections = {
  events: { type: 'event', title: 'Veranstaltungen' },
  venues: { type: 'venue', title: 'Orte' },
  spaces: { type: 'space', title: 'Räume' },
  organizations: { type: 'organization', title: 'Organisationen' },
  users: { type: 'user', title: 'Benutzer & Teams' },
  images: { type: 'image', title: 'Bilder' },
} as const satisfies Record<EntitySection, { type: string; title: string }>
export const factLabels = {
  username: 'Benutzername',
  description: 'Beschreibung',
  venue_name: 'Ort',
  space_name: 'Raum',
  event_dates: 'Termine',
  venues: 'Orte',
  spaces: 'Räume',
  events: 'Veranstaltungen',
  memberships: 'Teammitgliedschaften (einschließlich Einladungen)',
  image_links: 'Bildverknüpfungen',
  orphan: 'Ohne Verknüpfung',
}

export function entityFactLabel(section: EntitySection, field: keyof typeof factLabels): string {
  if (section === 'events' && field === 'venue_name') return 'Standardort'
  if (section === 'events' && field === 'space_name') return 'Standardraum'
  return factLabels[field]
}
