import type {
  GraphNode,
  GraphEdge,
  GraphEntityType,
  GraphRelationType,
  GraphResponse,
} from '../../shared/contracts'
const node = (type: GraphEntityType, number: number, label: string): GraphNode => {
  const key = `20000000-0000-4000-8000-${String(number).padStart(12, '0')}`
  const sections = {
    organization: 'organizations',
    venue: 'venues',
    space: 'spaces',
    event: 'events',
    user: 'users',
  }
  return {
    id: `${type}:${key}`,
    type,
    venue_scope: type === 'venue' ? (number === 4 ? 'shared' : 'organization') : null,
    key,
    label,
    subtitle: null,
    status: null,
    public_url: null,
    admin_url:
      type === 'event_date'
        ? `/activity?entity_key=${key}&entity_type=${type}`
        : `/${sections[type]}/${key}`,
  }
}
const nodes = [
  node('organization', 1, 'Kulturzentrum Rendsburg e.V.'),
  node('user', 2, 'Max Mustermann'),
  node('user', 3, 'Anna Beispiel'),
  node('venue', 4, 'Kulturzentrum Rendsburg'),
  node('venue', 5, 'St. Marien-Kirche Rendsburg'),
  node('space', 6, 'Großer Saal'),
  node('space', 7, 'Proberaum'),
  node('space', 8, 'Kirchensaal'),
  node('event', 9, 'Lange Nacht der Kirchen'),
  node('event', 10, 'Jazz im Hof'),
  node('event_date', 11, 'Lange Nacht · 20.09.2026'),
  node('event_date', 12, 'Jazz · 20.09.2026'),
]
const edge = (a: number, b: number, type: GraphRelationType, label: string): GraphEdge => ({
  id: `${type}:${a}:${b}`,
  source: nodes[a]!.id,
  target: nodes[b]!.id,
  type,
  label,
  direction: 'directed',
})
export const graphFixture: GraphResponse = {
  root: { type: 'organization', key: nodes[0]!.key },
  nodes,
  edges: [
    edge(1, 0, 'user_member_of_organization', 'Mitglied von'),
    edge(2, 0, 'user_member_of_organization', 'Mitglied von'),
    edge(0, 3, 'organization_has_venue', 'Betreibt'),
    edge(0, 4, 'organization_has_venue', 'Betreibt'),
    edge(3, 5, 'venue_has_space', 'Hat Raum'),
    edge(3, 6, 'venue_has_space', 'Hat Raum'),
    edge(4, 7, 'venue_has_space', 'Hat Raum'),
    edge(0, 8, 'organization_has_event', 'Organisiert'),
    edge(0, 9, 'organization_has_event', 'Organisiert'),
    edge(8, 4, 'event_uses_venue', 'Standardort'),
    edge(8, 10, 'event_has_date', 'Hat Termin'),
    edge(9, 11, 'event_has_date', 'Hat Termin'),
  ],
  truncated: false,
  max_nodes: 100,
  max_edges: 200,
}
export const graphPath = `/graph?root_type=organization&root_key=${nodes[0]!.key}&depth=2`
