import { expect, it } from 'vitest'
import { createAdminApi } from '../../app/utils/admin-api'
import {
  researchQueryRequestSchema,
  researchQueryResponseSchema,
} from '../../shared/research-execution'
import { conversationResponseSchema } from '../../shared/research-natural'

const token = 'a'.repeat(43)
const response = {
  kind: 'conversation',
  answer_text: 'Gerne.',
  language: 'de',
  conversation_id: token,
  interaction: { kind: 'acknowledgement', conversation: { act: 'acknowledge', reason: null } },
}
it('validates an ordinary social response without a fake Research payload', () => {
  expect(researchQueryResponseSchema.parse(response)).toEqual(response)
  for (const extra of [
    { plan: {} },
    { result: {} },
    { sql_provenance: [] },
    { conversation_context: {} },
  ]) {
    expect(conversationResponseSchema.safeParse({ ...response, ...extra }).success).toBe(false)
  }
  expect(
    conversationResponseSchema.safeParse({
      ...response,
      interaction: { ...response.interaction, research_plan: {} },
    }).success,
  ).toBe(false)
  expect(
    conversationResponseSchema.safeParse({
      ...response,
      interaction: { kind: 'greeting', conversation: { act: 'acknowledge', reason: null } },
    }).success,
  ).toBe(false)
})
it('sends only the current query and opaque token across the existing proxy route', async () => {
  let body: unknown
  const api = createAdminApi(async (_url, init) => {
    body = JSON.parse(String(init?.body))
    return new Response(JSON.stringify(response))
  })
  expect(await api.researchQuery('danke', undefined, undefined, undefined, token)).toEqual(response)
  expect(body).toEqual({ query: 'danke', conversation_id: token })
  expect(
    researchQueryRequestSchema.safeParse({ query: 'danke', conversation_id: 'readable-json' })
      .success,
  ).toBe(false)
})
