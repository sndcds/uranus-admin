import { detailFixture } from './entities'
import { activityFixture } from './activity'
import type { EntityDetail } from '../../shared/contracts'

/** Synthetic presentation fixture, not evidence of source contents or chronology. */
export function eventDetailFixture(): EntityDetail {
  const data = detailFixture('events')
  data.item.entity_name = 'Kulturnacht am Hafen'
  data.item.status = 'released'
  data.item.subtitle =
    'Musik, Lesungen und offene Ateliers · Nächster öffentlicher Termin: 25.09.2026 · 19:00 (Europe/Berlin)'
  data.item.public_url = `https://kulturbytes.de/de/veranstaltung/${data.item.entity_key}/20000000-0000-4000-8000-000000000002`
  data.item.image_url = `https://api.kulturbytes.de/api/image/20000000-0000-4000-8000-000000000002?width=320`
  data.item.facts.description =
    'Ein Abend für **Kultur und Begegnung** am Hafen. Gemeinsam mit lokalen Künstlerinnen und Künstlern öffnen wir die Türen für ein vielfältiges Programm.\n\n## Das erwartet dich\n\n- Musik auf der Hafenbühne\n- Lesungen und Gespräche\n- Offene Ateliers für alle Generationen\n\n> Der Eintritt ist frei. Bitte beachte die Hinweise am Veranstaltungsort.\n\nWeitere Informationen im [Programm](https://example.org/programm).'
  data.item.facts.event_dates = 1
  const kinds = ['event_date', 'organization', 'venue', 'space', 'image'] as const
  const sections = {
    organization: 'organizations',
    venue: 'venues',
    space: 'spaces',
    image: 'images',
  }
  data.related.items = kinds.map((kind) => {
    const item = { ...activityFixture.items.find((item) => item.entity_type === kind)! }
    if (kind === 'event_date') {
      item.entity_name = 'Kulturnacht – Abendprogramm'
      item.subtitle = 'Termin: 25.09.2026 · 19:00 (Europe/Berlin) · Hafenbühne'
    } else if (item.action)
      item.action = { ...item.action, href: `/${sections[kind]}/${item.entity_key}` }
    return item
  })
  data.related.pagination = { page: 1, page_size: 25, total: 5, pages: 1 }
  return data
}
