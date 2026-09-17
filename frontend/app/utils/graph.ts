import { entityTypes } from './entityPresentation'
import type { SimulationNodeDatum, SimulationLinkDatum } from 'd3-force'
import type { GraphNode, GraphEdge, GraphEntityType, GraphRelationType } from '#shared/contracts'
import { graphEntityTypeSchema } from '#shared/contracts'

export const nodePresentation = {
  organization: { ...entityTypes.organization, fill: '#f3e8ff', border: '#e9d5ff' },
  venue: { ...entityTypes.venue, fill: '#ecfdf5', border: '#d1fae5' },
  space: { ...entityTypes.space, fill: '#ecfeff', border: '#cffafe' },
  event: { ...entityTypes.event, fill: '#fff1f2', border: '#ffe4e6' },
  event_date: { ...entityTypes.event_date, fill: '#f5f3ff', border: '#ede9fe' },
  user: { ...entityTypes.user, fill: '#eff6ff', border: '#dbeafe' },
} as const satisfies Record<
  GraphEntityType,
  { label: string; icon: string; color: string; fill: string; border: string }
>

export const relationLabels: Record<GraphRelationType, string> = {
  organization_has_venue: 'Organisation → Ort',
  venue_has_space: 'Ort → Raum',
  organization_has_event: 'Organisation → Veranstaltung',
  event_has_date: 'Veranstaltung → Termin',
  event_uses_venue: 'Standardort',
  event_uses_space: 'Standardraum',
  event_date_uses_venue: 'Termin → Ort',
  event_date_uses_space: 'Termin → Raum',
  user_member_of_organization: 'Mitgliedschaften',
  user_invited_to_organization: 'Einladungen',
  organization_partner_request: 'Partneranfragen',
  organization_partner_of: 'Partnerschaften',
}
export type GraphSimulationNode = GraphNode & SimulationNodeDatum
export type GraphSimulationLink = Omit<GraphEdge, 'source' | 'target'> &
  SimulationLinkDatum<GraphSimulationNode>
export function graphDataToSimulation(nodes: GraphNode[], edges: GraphEdge[], root: string) {
  const others = nodes.filter((n) => n.id !== root)
  return {
    nodes: nodes.map((n) => {
      const i = others.findIndex((other) => other.id === n.id)
      const angle = (i / Math.max(others.length, 1)) * 2 * Math.PI - Math.PI / 2
      return {
        ...n,
        x: i < 0 ? 0 : Math.cos(angle) * 250,
        y: i < 0 ? 0 : Math.sin(angle) * 250,
      } as GraphSimulationNode
    }),
    links: edges.map((e) => ({ ...e })) as GraphSimulationLink[],
  }
}
export function filterGraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
  type: string,
  relation: string,
  root: string,
) {
  const visible = nodes.filter((n) => !type || n.type === type || n.id === root)
  const ids = new Set(visible.map((n) => n.id))
  return {
    nodes: visible,
    edges: edges.filter(
      (e) => ids.has(e.source) && ids.has(e.target) && (!relation || e.type === relation),
    ),
  }
}
export function graphHref(type: string, key: string) {
  return graphEntityTypeSchema.safeParse(type).success &&
    /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(key)
    ? `/graph?root_type=${type}&root_key=${key}&depth=2`
    : null
}
export function labelLines(label: string): string[] {
  const words = label.split(/\s+/)
  const lines = ['']
  for (const word of words) {
    const last = lines.length - 1
    if (lines[last] && `${lines[last]} ${word}`.length > 22) lines.push(word)
    else lines[last] = [lines[last], word].filter(Boolean).join(' ')
  }
  return lines
    .slice(0, 2)
    .map((line, i) =>
      line.length > 25 || (i === 1 && lines.length > 2) ? `${line.slice(0, 23)}…` : line,
    )
}
