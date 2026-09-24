import { entityFixture } from './entities'
import type { EntitySection } from '../../shared/contracts'

/** Existing fields only; deliberately long, synthetic identity and context values. */
export function collectionFixture(section: EntitySection) {
  const data = entityFixture(section)
  const base = data.items[0]!
  const names = {
    events: [
      'Kulturnacht am Hafen – Musik, Begegnungen und offene Werkstätten',
      'Lesung zwischen den Meeren',
      'Werkstatt für junge Klangkunst',
    ],
    organizations: [
      'Kulturverein für Begegnung und zeitgenössische Kunst am Hafen',
      'Literaturhaus Nord',
      'Initiative für Musik und Nachbarschaft',
    ],
    venues: ['Kulturhaus an der alten Hafenpromenade', 'Bibliothek am Wasser', 'Offene Werkstatt'],
    spaces: [
      'Werkstattraum für Musik und gemeinsame Projekte',
      'Lesesaal im Obergeschoss',
      'Atelier am Innenhof',
    ],
    users: [
      'Alexandra Beispiel',
      'teamkoordination.kultur-und-nachbarschaft@example.org',
      'Johannes Muster',
    ],
    images: [
      'Abstrakte Hafenlandschaft in Violett – Plakat der gemeinsamen Kulturnacht',
      'Programmübersicht und Lageplan',
      'Werkstatt am Wasser',
    ],
  } as const
  data.items = names[section].map((entity_name, index) => {
    const entity_key = `60000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`
    return {
      ...base,
      entity_key,
      entity_name,
      organization_name:
        section === 'organizations'
          ? entity_name
          : ['users', 'images'].includes(section)
            ? null
            : names.organizations[0],
      subtitle:
        section === 'events'
          ? 'Offenes Kulturprogramm · Eintritt frei'
          : section === 'organizations'
            ? 'Flensburg'
            : null,
      status:
        section === 'events'
          ? ['released', 'draft', 'review'][index]!
          : section === 'users'
            ? index
              ? 'inactive'
              : 'active'
            : null,
      email:
        section === 'users'
          ? index === 1
            ? entity_name
            : 'alexandra.beispiel.teamkoordination@example.org'
          : null,
      address: ['organizations', 'venues'].includes(section)
        ? 'An der alten Hafenpromenade 128, Hinterhaus am Innenhof, 24937 Flensburg'
        : null,
      image_url:
        section === 'spaces'
          ? null
          : section === 'users'
            ? `https://api.kulturbytes.de/api/user/${entity_key}/avatar/128`
            : `https://api.kulturbytes.de/api/image/${entity_key}?width=320`,
      public_url:
        section === 'events'
          ? `https://kulturbytes.de/de/veranstaltung/${entity_key}/${entity_key}`
          : section === 'venues'
            ? 'https://kulturbytes.de/de/ort/kulturhaus'
            : null,
      action: { ...base.action!, entity_key, href: `/${section}/${entity_key}` },
      facts: {
        ...base.facts,
        username: section === 'users' ? (index === 1 ? entity_name : 'alexandra-beispiel') : null,
        event_dates: section === 'events' ? index + 1 : null,
        venue_name: ['events', 'spaces'].includes(section) ? names.venues[0] : null,
        space_name: section === 'events' ? 'Saal A' : null,
        events: section === 'organizations' ? 12 : null,
        venues: section === 'organizations' ? 2 : null,
        memberships: ['organizations', 'users'].includes(section) ? 8 : null,
        spaces: section === 'venues' ? 3 : null,
        image_links: section === 'images' ? index : null,
        orphan: section === 'images' ? index === 0 : null,
      },
    }
  })
  data.pagination = { page: 1, page_size: 25, pages: 2, total: 28 }
  return data
}
