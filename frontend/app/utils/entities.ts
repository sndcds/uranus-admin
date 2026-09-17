import { entityTypes } from './entityPresentation'
import type { EntitySection } from '#shared/contracts'
export const entitySections = {
  events: { type: 'event', title: entityTypes.event.plural },
  venues: { type: 'venue', title: entityTypes.venue.plural },
  spaces: { type: 'space', title: entityTypes.space.plural },
  organizations: { type: 'organization', title: entityTypes.organization.plural },
  users: { type: 'user', title: 'Benutzer & Teams' },
  images: { type: 'image', title: entityTypes.image.plural },
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
