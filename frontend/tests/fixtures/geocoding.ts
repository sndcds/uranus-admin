import type { GeocodePage, GeocodeRequestDetail } from '../../shared/contracts'
export const geocodeDetail: GeocodeRequestDetail = {
  id: '00000000-0000-4000-8000-000000000901',
  entity_type: 'venue',
  entity_key: '00000000-0000-4000-8000-000000000020',
  entity_name: 'Test-Hafenbühne',
  source_address: 'Norderstraße 49, 24939 Flensburg, DEU',
  status: 'candidate',
  source_fingerprint: 'a'.repeat(64),
  query_fingerprint: 'b'.repeat(64),
  generation: 1,
  query_version: 1,
  scoring_version: 1,
  attempt_count: 1,
  checked_at: '2026-09-19T12:00:00Z',
  next_check_at: null,
  last_error: null,
  created_at: '2026-09-19T12:00:00Z',
  updated_at: '2026-09-19T12:00:00Z',
  candidate_count: 1,
  best_candidate: null,
  candidates: [
    {
      id: '00000000-0000-4000-8000-000000000902',
      rank: 1,
      latitude: 54.789123,
      longitude: 9.432123,
      display_name: 'Theater, Norderstraße 49, Flensburg',
      osm_type: 'way',
      osm_id: '123',
      provider_class: 'amenity',
      provider_type: 'theatre',
      provider_addresstype: 'amenity',
      provider_importance: 0.3,
      match_score: 1,
      match_reasons: [
        'country_exact',
        'postal_code_exact',
        'city_exact',
        'street_exact',
        'house_number_exact',
      ],
      address: {
        road: 'Norderstraße',
        house_number: '49',
        postcode: '24939',
        city: 'Flensburg',
        country_code: 'de',
      },
      osm_url: 'https://www.openstreetmap.org/way/123',
    },
  ],
}
geocodeDetail.best_candidate = geocodeDetail.candidates[0]!
export const geocodePage: GeocodePage = {
  items: [geocodeDetail],
  pagination: { page: 1, page_size: 50, total: 1, pages: 1 },
  counts: { candidate: 1 },
}

// Synthetic review scenario, not a production request or a claim about source coordinates.
export const geocodeWorkflowDetail: GeocodeRequestDetail = structuredClone(geocodeDetail)
geocodeWorkflowDetail.entity_name = 'Campelle Flensburg (Testdatensatz)'
geocodeWorkflowDetail.source_address = 'Thomas-Fincke-Straße 16, 24943 Flensburg, DEU'
geocodeWorkflowDetail.checked_at = '2026-09-22T08:58:00Z'
geocodeWorkflowDetail.candidates[0] = {
  ...geocodeWorkflowDetail.candidates[0]!,
  display_name: 'Campelle 16, Thomas-Fincke-Straße, Flensburg (Testvorschlag)',
  latitude: 54.774,
  longitude: 9.452,
  address: {
    road: 'Thomas-Fincke-Straße',
    house_number: '16',
    postcode: '24943',
    city: 'Flensburg',
    country_code: 'de',
  },
}
geocodeWorkflowDetail.best_candidate = geocodeWorkflowDetail.candidates[0]!
