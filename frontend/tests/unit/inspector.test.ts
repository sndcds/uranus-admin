import { expect, it } from 'vitest'
import { inspectorHref, inspectorIdentity, inspectorSection } from '../../app/utils/inspector'
import { entitySections } from '../../app/utils/entities'
import { graphHref } from '../../app/utils/graph'
const id = '20000000-0000-4000-8000-000000000001'
const other = '20000000-0000-4000-8000-000000000002'
it.each(Object.entries(entitySections))(
  'maps %s to the existing detail section',
  (section, entry) => {
    expect(inspectorSection(entry.type)).toBe(section)
    expect(inspectorHref(entry.type, id)).toBe(`/inspect/${entry.type}/${id}`)
  },
)
it('preserves composite identities and the existing membership graph root', () => {
  const key = `membership:${id}:${other}`
  expect(inspectorHref('team_membership', key)).toBe(
    `/inspect/team_membership/${encodeURIComponent(key)}`,
  )
  expect(graphHref('team_membership', key)).toBe(`/graph?root_type=user&root_key=${other}&depth=2`)
  expect(inspectorIdentity('partner_request', `partner-request:${id}:${other}`)?.key).toBe(
    `partner-request:${id}:${other}`,
  )
  expect(inspectorHref('event_date', id)).toBe(`/inspect/event_date/${id}`)
  expect(inspectorSection('event_date')).toBeUndefined()
  expect(graphHref('image', id)).toBeNull()
  expect(graphHref('social_publication', id)).toBeNull()
})
it.each([
  ['unknown', id],
  ['social_publication', id],
  ['user', '../users'],
  ['user', `${id}?secret=x`],
  ['team_membership', id],
  ['team_membership', `membership:${id}:${other}:extra`],
  ['partner_request', `membership:${id}:${other}`],
  ['partner_request', `partner-request:${id}:invalid`],
])('rejects unsupported or malformed navigation %s %s', (type, key) => {
  expect(inspectorIdentity(type, key)).toBeNull()
  expect(inspectorHref(type, key)).toBeNull()
})
