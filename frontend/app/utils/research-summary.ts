import type { ResearchExecutionResponse } from '#shared/contracts'
import { formatGroupingCoordinate, researchMetricLabels } from './research-answer'

/** Facts about returned rows only; never claims a semantic population or causality. */
export function summarizeResearchResult(response: ResearchExecutionResponse): string | null {
  const result = response.result
  const number = (n: number) => n.toLocaleString('de-DE')
  if (result.kind === 'needs_clarification') return null
  if (result.kind === 'count')
    return `Für diese Auswahl wurden ${number(result.value)} ${researchMetricLabels[result.metric]} gezählt.`
  if (result.kind === 'taxonomy')
    return `In den passenden Veranstaltungen werden ${number(result.total)} unterschiedliche ${{ genre: 'Genres', event_type: 'Veranstaltungstypen', category: 'Kategorien' }[result.taxonomy]} verwendet.`
  if (!result.items.length)
    return response.execution.semantic
      ? 'Für diese Frage wurden keine ausreichend passenden semantischen Treffer gefunden.'
      : 'Für diese Frage wurden keine passenden Ergebnisse gefunden.'
  if (result.kind === 'records')
    return response.execution.semantic
      ? `Die semantische Suche zeigt ${number(result.items.length)} passende Veranstaltungen; dies ist keine vollständige Zählung.`
      : `Für diese Frage werden ${number(result.items.length)} passende Datensätze angezeigt.`
  if (result.kind === 'spatial')
    return `Die räumliche Auswertung zeigt ${number(result.items.length)} Datensätze mit bekannter Position.`
  const maximum = Math.max(...result.items.map((item) => item.value))
  const highest = result.items.filter((item) => item.value === maximum)
  const metric = {
    event_count: 'Veranstaltungen',
    occurrence_count: 'Terminen',
    venue_count: 'Orten',
    organization_count: 'Organisationen',
  }[result.metric]
  if (highest.length > 1)
    return `${number(highest.length)} der angezeigten ${result.kind === 'grouped' ? 'Kombinationen' : 'Gruppen'} teilen sich mit ${number(maximum)} ${metric} den höchsten angezeigten Wert.`
  const item = highest[0]!
  const label =
    'coordinates' in item
      ? item.coordinates.map((c) => formatGroupingCoordinate(c.dimension, c.name)).join(' / ')
      : 'target' in item
        ? item.target.label
        : item.name
  return `Unter den angezeigten ${result.kind === 'grouped' ? 'Kombinationen' : result.kind === 'comparison' ? 'Vergleichszielen' : 'Gruppen'} hat „${label}“ mit ${number(maximum)} ${metric} den höchsten Wert.`
}
