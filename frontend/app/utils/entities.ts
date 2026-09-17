import { entityTypes } from './entityPresentation'
import type { EntitySection, EntitySearchType, TemporalFilter } from '#shared/contracts'
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

export function entityFactLabel(section: EntitySection, field: keyof typeof factLabels): string {
  if (section === 'events' && field === 'venue_name') return 'Standardort'
  if (section === 'events' && field === 'space_name') return 'Standardraum'
  return factLabels[field]
}

export const entitySearchPlaceholders: Record<EntitySearchType, string> = {
  user: 'Nach Name, Benutzername, E-Mail oder UUID suchen …',
  organization: 'Nach Organisation, E-Mail, Ort, PLZ oder UUID suchen …',
  venue: 'Nach Ort, Adresse, E-Mail oder UUID suchen …',
  space: 'Nach Raum, Ort oder UUID suchen …',
  event: 'Nach Veranstaltung, Untertitel, externer ID oder UUID suchen …',
  image: 'Nach Bild, Dateiname, Alt-Text oder UUID suchen …',
}

export function supportsTemporal(type: EntitySearchType): boolean {
  return type !== 'user' && type !== 'image'
}
export const temporalLabels: Record<TemporalFilter, string> = {
  upcoming: 'Mit bevorstehenden Terminen',
  past: 'Mit vergangenen Terminen',
}
export function temporalFromQuery(value: unknown): TemporalFilter | '' {
  return value === 'upcoming' || value === 'past' ? value : ''
}
