import type { GeoArea, GeoAreaSearchItem } from '../../shared/contracts'
export const geoArea: GeoArea = {
  id: '10000000-0000-4000-8000-000000000001',
  source: 'osm',
  source_type: 'relation',
  source_id: '27020',
  name: 'Flensburg',
  display_name: 'Flensburg, Schleswig-Holstein, Deutschland',
  country_code: 'de',
  admin_level: 6,
  kind: 'city',
  provider_class: 'boundary',
  provider_type: 'administrative',
  provider_addresstype: 'city',
  bbox: [9, 54, 10, 55],
  hierarchy: { city: 'Flensburg', state: 'Schleswig-Holstein', country: 'Deutschland' },
  fetched_at: '2026-09-18T10:00:00Z',
}
export const geoSearchItem: GeoAreaSearchItem = {
  ...geoArea,
  provider: 'osm',
  osm_type: 'relation',
  osm_id: '27020',
  eligible_for_scope: true,
}
