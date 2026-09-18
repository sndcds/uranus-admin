import type { GeoAreaKind, GeoAreaSearchItem, GeoArea, EntitySearchType } from '#shared/contracts'

export const supportsGeoScope = (path: string) =>
  /^\/(events|venues|spaces|organizations)\/?$/.test(path)

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
