import type { GeoAreaKind, GeoAreaSearchItem, GeoArea, EntitySearchType } from '#shared/contracts'

export const supportsGeoScope = (path: string) =>
  /^\/(events|venues|spaces|organizations|activity|findings|statistics|graph)?\/?$/.test(path)

export const geoKindLabels: Record<GeoAreaKind, string> = {
  country: 'Land',
  region: 'Region',
  county: 'Kreis',
  municipality: 'Gemeinde',
  city: 'Stadt',
  district: 'Bezirk',
  other: 'Gebiet',
}
export function geoAreaLabel(area: GeoAreaSearchItem | GeoArea): string {
  const hierarchy = Object.values(area.hierarchy).filter((name) => name !== area.name)
  return [geoKindLabels[area.kind], ...new Set(hierarchy)].join(' · ')
}

export const supportsGeoEntity = (type: EntitySearchType) =>
  ['event', 'venue', 'space', 'organization'].includes(type)

export const spatialTypes = ['organization', 'venue', 'space', 'event', 'event_date'] as const
export const isSpatialType = (type: string) => spatialTypes.some((kind) => kind === type)

/** Only paginated list URLs accept page; analytics and graph do not. */
export const geoPagination = (path: string) =>
  /^\/(events|venues|spaces|organizations|activity|findings)\/?$/.test(path)
