import { afterEach, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { computed, defineComponent, h } from 'vue'
import EntityTypeBadge from '../../app/components/EntityTypeBadge.vue'
import StatusBadge from '../../app/components/StatusBadge.vue'
import ActivityRow from '../../app/components/ActivityRow.vue'
import ActivityThumbnail from '../../app/components/ActivityThumbnail.vue'
import { activityPageSchema } from '../../shared/contracts'
import AppIcon from '../../app/components/AppIcon.vue'
import RecordMarkLink from '../../app/components/RecordMarkLink.vue'
import {
  activityTypes,
  activityGroups,
  activityName,
  activityCounts,
  activityImagePreviewUrl,
  activityStatus,
} from '../../app/utils/activity'
import { calendarDay, dayLabel, activityTime, dateTime } from '../../app/utils/presentation'
import { activityFixture, activityObservedAt } from '../fixtures/activity'

const first = activityFixture.items[0]!
const NuxtLink = defineComponent({
  props: ['to'],
  setup(props, { slots }) {
    return () =>
      h(
        'a',
        {
          href:
            typeof props.to === 'string'
              ? props.to
              : `${props.to.path}?${new URLSearchParams(props.to.query)}`,
        },
        slots.default?.(),
      )
  },
})
function row(item = first) {
  vi.stubGlobal('computed', computed)
  return mount(ActivityRow, {
    props: { item, observedAt: activityObservedAt, grouped: true },
    global: {
      components: { AppIcon, RecordMarkLink, ActivityThumbnail, EntityTypeBadge, StatusBadge },
      stubs: { NuxtLink },
    },
  })
}
afterEach(() => vi.unstubAllGlobals())

it.each(Object.entries(activityTypes))(
  'presents %s with a German badge and decorative icon',
  (type, presentation) => {
    const wrapper = row({ ...first, entity_type: type as typeof first.entity_type })
    expect(wrapper.text()).toContain(presentation.label)
    expect(wrapper.get('svg').attributes('aria-hidden')).toBe('true')
    expect(wrapper.element.tagName).toBe('LI')
  },
)

it('keeps names prominent, organization fallback accurate, status compact and targets intact', () => {
  const wrapper = row({ ...first, organization_name: null })
  expect(wrapper.get('h4').text()).toBe(first.entity_name)
  expect(wrapper.text()).toContain('Keine eindeutige Organisation')
  expect(wrapper.text()).toContain('Veröffentlicht')
  expect(wrapper.get('time').attributes('datetime')).toBe(first.created_at)
  expect(wrapper.get('time').attributes('title')).toContain(dateTime(first.created_at))
  const links = wrapper.findAll('a')
  expect(links[0]!.attributes('href')).toBe(first.action!.href)
  expect(links[0]!.attributes('aria-label')).toContain(first.entity_name)
  const mark = new URL(links[1]!.attributes('href'), 'http://test')
  expect(mark.pathname).toBe('/marks')
  expect(mark.searchParams.get('entity_type')).toBe(first.entity_type)
  expect(mark.searchParams.get('entity_key')).toBe(first.entity_key)
  expect(links[1]!.text()).toBe('Markierungen & Notizen')
})

it('preserves a real organization and unknown status; omits unavailable action/time', () => {
  const wrapper = row({ ...first, status: 'custom-source-status', created_at: null, action: null })
  expect(wrapper.text()).toContain('Kulturverein Nord')
  expect(wrapper.text()).toContain('custom-source-status')
  expect(wrapper.text()).toContain('Ohne Zeitstempel')
  expect(wrapper.find('time').exists()).toBe(false)
  expect(wrapper.findAll('a')).toHaveLength(1)
  expect(activityStatus(null)).toBeNull()
  for (const value of ['constructor', '__proto__', 'toString'])
    expect(activityStatus(value)).toBe(value)
})

it('uses honest title fallbacks without displaying UUIDs as names', () => {
  for (const name of ['', '  ', first.entity_key, '10000000-0000-4000-8000-000000000010']) {
    expect(activityName({ ...first, entity_name: name })).toBe('Termin ohne Anzeigenamen')
  }
  expect(activityName({ ...first, entity_name: '  Offene Bühne  ' })).toBe('Offene Bühne')
})

it('groups only the current page, keeping API order and distinguishing today, yesterday and older dates', () => {
  const groups = activityGroups(activityFixture)
  expect(groups.map((group) => group.label)).toEqual(['Heute', 'Gestern', '13. September 2026'])
  expect(groups.map((group) => group.items.length)).toEqual([12, 5, 3])
  expect(groups.flatMap((group) => group.items)).toEqual(activityFixture.items)
  expect(activityCounts(activityFixture.items).reduce((sum, item) => sum + item.count, 0)).toBe(20)
  expect(activityFixture.pagination.total).toBe(80)
})

it('never assigns missing timestamps to today or groups the unknown stream by date', () => {
  const unknown = { ...activityFixture, timestamp_state: 'unknown' as const }
  expect(activityGroups(unknown)).toEqual([{ key: 'unknown', label: null, items: unknown.items }])
  const missing = activityGroups({ ...activityFixture, items: [{ ...first, created_at: null }] })
  expect(missing[0]!.label).toBe('Ohne belegten Zeitpunkt')
  expect(activityGroups({ ...activityFixture, items: [] })).toEqual([])
})

it('uses Berlin calendar boundaries even when the browser is in a different timezone', () => {
  expect(calendarDay('2026-09-14T22:15:00Z')).toBe('2026-09-15')
  expect(dayLabel('2026-09-14T22:15:00Z', activityObservedAt)).toBe('Heute')
  expect(activityTime('2026-09-14T22:15:00Z', activityObservedAt)).toBe('00:15')
  expect(activityTime('2026-09-13T16:22:00Z', activityObservedAt)).toBe('13.09. · 18:22')
  expect(activityTime(null, activityObservedAt)).toBe('Ohne Zeitstempel')
  expect(calendarDay('invalid')).toBeNull()
})

it.each([
  ['2026-03-29T00:15:00+01:00', '2026-03-30T00:15:00+02:00'],
  ['2026-10-25T00:15:00+02:00', '2026-10-26T00:15:00+01:00'],
  ['2025-12-31T12:00:00Z', '2026-01-01T12:00:00Z'],
])(
  'computes yesterday as a calendar day across DST and year boundaries (%s)',
  (value, observed) => {
    expect(dayLabel(value, observed)).toBe('Gestern')
  },
)

it('does not promote partner UUID pairs to names or discard a known partner name', () => {
  const id = '10000000-0000-4000-8000-000000000010'
  const item = { ...first, entity_type: 'partner_request' as const }
  expect(activityName({ ...item, entity_name: `${id} → ${first.entity_key}` })).toBe(
    'Partneranfrage ohne Anzeigenamen',
  )
  expect(activityName({ ...item, entity_name: `Kulturverein → ${id}` })).toBe(
    `Kulturverein → ${id}`,
  )
})

it('shows public previews, secured external links and image failure fallback', async () => {
  const item = {
    ...first,
    image_url:
      'https://api.kulturbytes.de/api/image/20000000-0000-7000-8000-000000000001?width=320',
    public_url: 'https://kulturbytes.de/de/ort/hafenbuehne',
    subtitle: 'Termin: 15.09.2026 · 19:00 · Hafenbühne',
    address: 'Hafenstraße 3, Flensburg',
  }
  const wrapper = row(item)
  expect(wrapper.text()).toContain(item.subtitle)
  expect(wrapper.text()).toContain(item.address)
  expect(wrapper.text()).toContain('Im Admin ansehen')
  const external = wrapper.get('a[target="_blank"]')
  expect(external.attributes('href')).toBe(item.public_url)
  expect(external.attributes('rel')).toBe('noopener noreferrer')
  expect(external.attributes('aria-label')).toContain('neuer Tab')
  const image = wrapper.get('img')
  expect(image.attributes('src')).toBe(item.image_url)
  expect(image.attributes('loading')).toBe('lazy')
  expect(image.attributes('decoding')).toBe('async')
  expect(image.attributes('alt')).toBe(item.entity_name)
  expect(image.attributes('referrerpolicy')).toBe('no-referrer')
  expect(image.attributes('crossorigin')).toBe('anonymous')
  await image.trigger('error')
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.find('svg').exists()).toBe(true)
})

it('rejects unsafe external preview URLs and accepts absent previews', () => {
  expect(activityPageSchema.safeParse(activityFixture).success).toBe(true)
  for (const url of [
    'javascript:alert(1)',
    'https://evil.test/x',
    'https://kulturbytes.de.evil.test/de/ort/foo',
    'https://kulturbytes.de/de/ort/foo?token=secret',
  ]) {
    expect(
      activityPageSchema.safeParse({ ...activityFixture, items: [{ ...first, public_url: url }] })
        .success,
    ).toBe(false)
    expect(
      activityPageSchema.safeParse({ ...activityFixture, items: [{ ...first, image_url: url }] })
        .success,
    ).toBe(false)
  }
})

it('keeps image metadata and actions without a preview or public page', () => {
  const item = activityFixture.items.find((item) => item.entity_type === 'image')!
  const wrapper = row(item)
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.find('a[target="_blank"]').exists()).toBe(false)
  expect(wrapper.text()).toContain(item.entity_name)
  expect(wrapper.text()).toContain('Im Admin ansehen')
  expect(wrapper.text()).toContain('Markierungen')
})

it('retries a changed image source after an image error', async () => {
  const item = activityFixture.items.find((item) => item.entity_type === 'image')!
  const imageUrl = `https://api.kulturbytes.de/api/image/${item.entity_key}?width=320`
  const wrapper = row({ ...item, image_url: imageUrl })
  await wrapper.get('img').trigger('error')
  expect(wrapper.find('img').exists()).toBe(false)
  await wrapper.setProps({
    item: { ...item, image_url: imageUrl.replace(item.entity_key, first.entity_key) },
  })
  expect(wrapper.find('img').exists()).toBe(true)
})

it('validates new thumbnail URLs and supports existing square URLs during rollout', () => {
  for (const query of ['width=320', 'width=320&ratio=16%3A9', 'width=160&ratio=1%3A1']) {
    const image_url = `https://api.kulturbytes.de/api/image/${first.entity_key}?${query}`
    expect(
      activityPageSchema.safeParse({ ...activityFixture, items: [{ ...first, image_url }] })
        .success,
    ).toBe(true)
  }
  for (const query of ['width=960&ratio=16%3A9', 'width=320&token=secret']) {
    const image_url = `https://api.kulturbytes.de/api/image/${first.entity_key}?${query}`
    expect(
      activityPageSchema.safeParse({ ...activityFixture, items: [{ ...first, image_url }] })
        .success,
    ).toBe(false)
  }
})

it('only derives uncropped modal previews from validated public thumbnails', () => {
  const base = `https://api.kulturbytes.de/api/image/${first.entity_key}`
  for (const query of ['width=320', 'width=320&ratio=16%3A9', 'width=160&ratio=1%3A1']) {
    expect(activityImagePreviewUrl(`${base}?${query}`)).toBe(`${base}?width=1280`)
  }
  for (const source of [
    undefined,
    null,
    'https://evil.test/image',
    `${base}?width=320&token=secret`,
  ]) {
    expect(activityImagePreviewUrl(source)).toBeNull()
  }
})
