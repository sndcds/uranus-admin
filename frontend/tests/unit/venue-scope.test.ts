import { afterEach, expect, it } from 'vitest'
import { enableAutoUnmount, mount } from '@vue/test-utils'
import VenueScopeBadge from '../../app/components/VenueScopeBadge.vue'
import EntityCollectionRow from '../../app/components/EntityCollectionRow.vue'
import EntityHero from '../../app/components/EntityHero.vue'
import ActivityRow from '../../app/components/ActivityRow.vue'
import PageHeader from '../../app/components/PageHeader.vue'
import {
  activityPageSchema,
  entityRecordSchema,
  entitySearchItemSchema,
  globalSearchItemSchema,
  graphNodeSchema,
  venueScopeSchema,
} from '../../shared/contracts'
import { entityFixture } from '../fixtures/entities'
import { createAdminApi } from '../../app/utils/admin-api'

enableAutoUnmount(afterEach)
const labels = [
  ['shared', 'Eigener Ort'],
  ['organization', 'Provisorischer Ort (nicht eigener Ort)'],
] as const
const global = {
  components: { PageHeader },
  stubs: {
    SqlProvenanceButton: true,
    ActivityThumbnail: true,
    EntityTypeBadge: true,
    AppIcon: true,
    OperationTime: true,
    GraphLink: true,
    RecordMarkLink: true,
    InlineAlert: true,
    NuxtLink: { template: '<a><slot /></a>' },
  },
}
it.each(labels)('presents %s as an explicit neutral type with readable text', (scope, label) => {
  const badge = mount(VenueScopeBadge, { props: { scope } })
  expect(badge.text()).toBe(label)
  expect(badge.attributes('data-venue-scope')).toBe(scope)
  expect(badge.classes()).toContain('whitespace-normal')
  expect(badge.classes()).toContain('bg-slate-100')
  const item = { ...entityFixture('venues').items[0]!, venue_scope: scope }
  const collection = mount(EntityCollectionRow, { props: { item, section: 'venues' }, global })
  expect(collection.get('[data-venue-scope]').text()).toBe(label)
  expect(collection.get('[data-venue-scope]').element.closest('dl')).toBeNull()
  const hero = mount(EntityHero, { props: { item, section: 'venues' }, global })
  expect(hero.get('header [data-venue-scope]').text()).toBe(label)
  for (const relation of [false, true]) {
    const activity = mount(ActivityRow, {
      props: { item, relation, observedAt: '2026-09-24T10:00:00Z' },
      global,
    })
    expect(activity.get('[data-venue-scope]').text()).toBe(label)
  }
})
it('does not infer scope from organization or apply venue scope to events/spaces', () => {
  for (const section of ['venues', 'events', 'spaces'] as const) {
    const item = {
      ...entityFixture(section).items[0]!,
      venue_scope: section === 'venues' ? null : ('organization' as const),
    }
    for (const component of [EntityCollectionRow, EntityHero]) {
      expect(
        mount(component, { props: { item, section }, global }).find('[data-venue-scope]').exists(),
      ).toBe(false)
    }
    expect(
      mount(ActivityRow, { props: { item, observedAt: '2026-09-24T10:00:00Z' }, global })
        .find('[data-venue-scope]')
        .exists(),
    ).toBe(false)
  }
})
it('all venue read schemas reject unknown values instead of interpreting standard as shared', () => {
  for (const scope of ['standard', 'unknown', 'SHARED']) {
    expect(venueScopeSchema.safeParse(scope).success).toBe(false)
    for (const schema of [
      activityPageSchema.shape.items.element,
      entityRecordSchema,
      entitySearchItemSchema,
      globalSearchItemSchema,
      graphNodeSchema,
    ]) {
      expect(schema.shape.venue_scope.safeParse(scope).success).toBe(false)
    }
  }
  for (const scope of [undefined, null, 'organization', 'shared']) {
    expect(entityRecordSchema.shape.venue_scope.safeParse(scope).success).toBe(true)
  }
})
it('the API client reports invalid_response for an unsupported source scope', async () => {
  const item = entityFixture('venues').items[0]!
  const fetcher = async () =>
    new Response(
      JSON.stringify({
        items: [
          {
            entity_type: 'venue',
            entity_key: item.entity_key,
            label: item.entity_name,
            subtitle: null,
            status: null,
            action: item.action,
            venue_scope: 'standard',
          },
        ],
      }),
    )
  await expect(
    createAdminApi(fetcher).entitySearch({ entity_type: 'venue', q: 'Venue' }),
  ).rejects.toMatchObject({ failure: { code: 'invalid_response' } })
})
