import type { GraphEdge, GraphNode, ResearchDetail, ResearchRecord } from '#shared/contracts'

/** Only public relationships returned with this dossier page; never infer ownership from use. */
export function researchRelations(detail: ResearchDetail) {
  const nodes = new Map<string, GraphNode>()
  const edges = new Map<string, GraphEdge>()
  function node(type: GraphNode['type'], key: string, label: string) {
    const id = `${type}:${key}`
    nodes.set(id, {
      id,
      type,
      key,
      label,
      subtitle: null,
      status: null,
      admin_url: null,
      public_url: null,
    })
    return id
  }
  function edge(source: string, target: string, type: GraphEdge['type'], label: string) {
    const id = `${type}:${source}:${target}`
    edges.set(id, { id, source, target, type, label, direction: 'directed' })
  }
  function event(item: ResearchRecord) {
    const id = node('event', item.entity_key, item.name)
    if (item.organization_id && item.organization_name)
      edge(
        node('organization', item.organization_id, item.organization_name),
        id,
        'organization_has_event',
        'veranstaltet',
      )
    if (item.venue_id && item.venue_name)
      edge(id, node('venue', item.venue_id, item.venue_name), 'event_uses_venue', 'findet statt in')
    if (item.space_id && item.space_name)
      edge(id, node('space', item.space_id, item.space_name), 'event_uses_space', 'nutzt Raum')
  }
  const root = node(detail.item.entity_type, detail.item.entity_key, detail.item.name)
  if (detail.item.entity_type === 'event') {
    event(detail.item)
    for (const date of detail.dates.items) {
      const id = node(
        'event_date',
        date.id,
        `${date.start_date} ${date.start_time?.slice(0, 5) ?? ''}`,
      )
      edge(root, id, 'event_has_date', 'hat Termin')
      if (date.venue_id && date.venue_name)
        edge(
          id,
          node('venue', date.venue_id, date.venue_name),
          'event_date_uses_venue',
          'findet statt in',
        )
      if (date.space_id && date.space_name)
        edge(
          id,
          node('space', date.space_id, date.space_name),
          'event_date_uses_space',
          'nutzt Raum',
        )
    }
  } else {
    for (const item of detail.events.items) event(item)
  }
  // Match the existing graph's rendering bounds; the complete visible relation list stays available.
  const graphNodes = [...nodes.values()].slice(0, 100)
  const ids = new Set(graphNodes.map((n) => n.id))
  return {
    root,
    nodes: graphNodes,
    edges: [...edges.values()].filter((e) => ids.has(e.source) && ids.has(e.target)).slice(0, 200),
    relations: [...edges.values()].map((e) => ({
      ...e,
      sourceNode: nodes.get(e.source)!,
      targetNode: nodes.get(e.target)!,
    })),
    truncated: nodes.size > 100 || edges.size > 200,
  }
}
