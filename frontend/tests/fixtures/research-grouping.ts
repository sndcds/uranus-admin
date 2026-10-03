import { researchExecutionResponseSchema } from '../../shared/research-execution'
import response from './research-grouping-response.json' with { type: 'json' }

// Captured from the normal backend route; its SQL/bindings are checked against
// the actual repository execution in test_research_grouping_flow.py.
export function groupedExecutionResponse() {
  return researchExecutionResponseSchema.parse(response)
}
