import type { ResearchSuggestions } from '../../shared/contracts'

// Synthetic test data only; the production feature has no suggestion catalogue.
export const researchSuggestions: ResearchSuggestions = {
  request_id: '10000000-0000-4000-8000-000000000010',
  suggestions: [
    {
      id: '10000000-0000-4000-8000-000000000011',
      query: 'Wie viele Veranstaltungen gab es in Flensburg im August?',
      position: 1,
    },
  ],
}
export const suggestionReceipt = '10000000-0000-4000-8000-000000000012'
