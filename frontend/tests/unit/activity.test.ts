import { afterEach, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { computed, defineComponent, h } from 'vue'
import EntityTypeBadge from '../../app/components/EntityTypeBadge.vue'
import StatusBadge from '../../app/components/StatusBadge.vue'
import ActivityRow from '../../app/components/ActivityRow.vue'
import ActivityThumbnail from '../../app/components/ActivityThumbnail.vue'
import { activityPageSchema } from '../../shared/contracts'
import AppIcon from '../../app/components/AppIcon.vue'
import InlineAlert from '../../app/components/InlineAlert.vue'
import RecordMarkLink from '../../app/components/RecordMarkLink.vue'
import {
  activityTypes,
  activityGroups,
  activityName,
  activityCounts,
  activityImagePreviewUrl,
  activityStatus,
  activityMapUrl,
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
      components: {
        AppIcon,
        InlineAlert,
        RecordMarkLink,
        ActivityThumbnail,
        EntityTypeBadge,
        StatusBadge,
      },
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
  const mark = new URL(wrapper.get('a[href^="/marks"]').attributes('href'), 'http://test')
  expect(mark.pathname).toBe('/marks')
  expect(mark.searchParams.get('entity_type')).toBe(first.entity_type)
  expect(mark.searchParams.get('entity_key')).toBe(first.entity_key)
  expect(wrapper.get('a[href^="/marks"]').text()).toBe('Markierungen & Notizen')
})

it('preserves a real organization and unknown status; omits unavailable action/time', () => {
  const wrapper = row({ ...first, status: 'custom-source-status', created_at: null, action: null })
  expect(wrapper.text()).toContain('Kulturverein Nord')
  expect(wrapper.text()).toContain('custom-source-status')
  expect(wrapper.text()).toContain('Ohne Zeitstempel')
  expect(wrapper.find('time').exists()).toBe(false)
  expect(wrapper.findAll('a')).toHaveLength(2)
  expect(wrapper.get('a[href^="/graph"]').text()).toContain('Beziehungen')
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
  expect(wrapper.text()).toContain('Öffnen')
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
  expect(wrapper.text()).toContain('Öffnen')
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

it('shows user email and verified avatar while preserving the image fallback', async () => {
  const image_url = `https://api.kulturbytes.de/api/user/${first.entity_key}/avatar/128`
  const item = {
    ...first,
    entity_type: 'user' as const,
    email: 'operator@example.invalid',
    image_url,
  }
  expect(activityPageSchema.safeParse({ ...activityFixture, items: [item] }).success).toBe(true)
  const wrapper = row(item)
  expect(wrapper.text()).toContain('E-Mail: operator@example.invalid')
  expect(wrapper.get('img').attributes('src')).toBe(image_url)
  expect(wrapper.get('img').attributes('loading')).toBe('lazy')
  expect(activityImagePreviewUrl(image_url)).toBe(image_url.replace('/128', '/512'))
  await wrapper.get('img').trigger('error')
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.text()).toContain('operator@example.invalid')
  expect(wrapper.text()).toContain('Markierungen')
})

it('adds organization logo padding, source address and a safe OSM coordinate link', () => {
  const item = {
    ...first,
    entity_type: 'organization' as const,
    image_url: `https://api.kulturbytes.de/api/image/${first.entity_key}?width=320`,
    address: 'Hafenstraße 3, 24937 Flensburg',
    location: { latitude: 54.79, longitude: 9.43 },
  }
  const wrapper = row(item)
  expect(wrapper.get('button[aria-haspopup="dialog"]').classes()).toContain('p-3')
  expect(wrapper.get('img').classes()).toContain('h-auto')
  expect(
    row({ ...item, entity_type: 'venue' })
      .get('button[aria-haspopup="dialog"]')
      .classes(),
  ).toContain('p-3')
  expect(wrapper.text()).toContain(item.address)
  const link = wrapper.get('a[href^="https://www.openstreetmap.org/"]')
  expect(link.attributes('href')).toBe(
    'https://www.openstreetmap.org/?mlat=54.79&mlon=9.43#map=17/54.79/9.43',
  )
  expect(link.attributes('target')).toBe('_blank')
  expect(link.attributes('rel')).toBe('noopener noreferrer')
  expect(link.attributes('referrerpolicy')).toBe('no-referrer')
  expect(
    row({ ...item, entity_type: 'image' })
      .get('button[aria-haspopup="dialog"]')
      .classes(),
  ).not.toContain('p-3')
  expect(
    row({ ...item, location: null })
      .find('a[href^="https://www.openstreetmap.org/"]')
      .exists(),
  ).toBe(false)
})

it('rejects unsafe avatar endpoints and invalid map coordinates', () => {
  for (const image_url of [
    `https://api.kulturbytes.de/api/user/${first.entity_key}/avatar/128?token=secret`,
    `https://evil.test/api/user/${first.entity_key}/avatar/128`,
    `https://api.kulturbytes.de/api/user/${first.entity_key}/avatar/999`,
  ]) {
    expect(
      activityPageSchema.safeParse({ ...activityFixture, items: [{ ...first, image_url }] })
        .success,
    ).toBe(false)
    expect(activityImagePreviewUrl(image_url)).toBeNull()
  }
  for (const location of [
    null,
    undefined,
    { latitude: 91, longitude: 0 },
    { latitude: 0, longitude: Infinity },
    { latitude: NaN, longitude: 0 },
  ]) {
    expect(activityMapUrl(location)).toBeNull()
  }
  expect(activityMapUrl({ latitude: 0, longitude: 0 })).toBe(
    'https://www.openstreetmap.org/?mlat=0&mlon=0#map=17/0/0',
  )
  expect(row({ ...first, email: null }).text()).not.toContain('E-Mail:')
})

it.each([
  ['draft', 'Entwurf'],
  ['review', 'In Prüfung'],
])('renders the backend %s next-date subtitle without a public link', (status, badge) => {
  const item = {
    ...first,
    entity_type: 'event' as const,
    status,
    subtitle: 'Nächster Termin: 21.09.2026 · 18:00 (Europe/Berlin)',
    notice: 'Dieser noch unveröffentlichte Event findet schon in 3 Tagen statt.',
    public_url: null,
  }
  const wrapper = row(item)
  expect(wrapper.get('[role="status"]').text()).toBe(item.notice)
  expect(wrapper.text()).toContain(item.subtitle)
  expect(wrapper.text()).toContain(badge)
  expect(wrapper.find('a[href^="https://kulturbytes.de/"]').exists()).toBe(false)
  expect(wrapper.get('time').attributes('datetime')).toBe(item.created_at)
  expect(wrapper.get('time').text()).toBe(activityTime(item.created_at, activityObservedAt))
})

it('renders the backend notice as a separate accessible warning and clears it when absent', async () => {
  const subtitle = 'Nächster Termin: 21.09.2026 · 18:00 (Europe/Berlin)'
  const notice = 'Dieser noch unveröffentlichte Event findet schon in 3 Tagen statt.'
  const item = {
    ...first,
    entity_type: 'event' as const,
    status: 'draft',
    subtitle,
    notice,
    public_url: null,
  }
  const wrapper = row(item)
  const warning = wrapper.get('[role="status"]')
  expect(warning.text()).toBe(notice)
  expect(warning.classes()).toContain('bg-amber-50')
  expect(warning.get('svg').attributes('aria-hidden')).toBe('true')
  expect(warning.element.previousElementSibling?.textContent).toBe(subtitle)
  expect(wrapper.get('[role="status"]').text()).not.toContain(subtitle)
  expect(wrapper.text()).toContain('Entwurf')
  expect(wrapper.find('a[href^="https://kulturbytes.de/"]').exists()).toBe(false)
  const created = wrapper.get('time').html()
  for (const absent of [null, undefined]) {
    await wrapper.setProps({ item: { ...item, notice: absent } })
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
    expect(wrapper.text()).toContain(subtitle)
    expect(wrapper.get('time').html()).toBe(created)
  }
})

it('preserves optional notices in the shared contract and public links on released rows', () => {
  for (const notice of [
    undefined,
    null,
    'Dieser noch unveröffentlichte Event findet heute statt.',
  ]) {
    const parsed = activityPageSchema.parse({ ...activityFixture, items: [{ ...first, notice }] })
    expect(parsed.items[0]!.notice).toBe(notice)
  }
  const item = {
    ...first,
    entity_type: 'event' as const,
    status: 'released',
    subtitle: 'Nächster öffentlicher Termin: 20.09.2026 · 18:00 (Europe/Berlin)',
    notice: null,
    public_url: `https://kulturbytes.de/de/veranstaltung/${first.entity_key}/019954ea-0000-7000-8000-000000000001`,
  }
  const wrapper = row(item)
  expect(wrapper.find('[role="status"]').exists()).toBe(false)
  expect(wrapper.text()).toContain(item.subtitle)
  expect(wrapper.text()).toContain('Veröffentlicht')
  expect(wrapper.get('a[href^="https://kulturbytes.de/"]').attributes('href')).toBe(item.public_url)
  expect(wrapper.get('time').attributes('datetime')).toBe(item.created_at)
})

it.each(['user', 'team_membership'] as const)(
  'renders the authoritative %s label, including email and the last-resort UUID',
  (entity_type) => {
    for (const entity_name of ['Max Mustermann', 'max', 'no-name@example.org', first.entity_key]) {
      const wrapper = row({ ...first, entity_type, entity_name })
      expect(wrapper.get('h4').text()).toBe(entity_name)
      wrapper.unmount()
    }
  },
)

it('uses a button-styled Öffnen link for relation records without reverting to admin-view wording or time-only dates', async () => {
  const wrapper = row()
  await wrapper.setProps({ dense: true, relation: true })
  const open = wrapper.get(`a[href="${first.action!.href}"]`)
  expect(open.text()).toBe('Öffnen')
  expect(open.classes()).toContain('button')
  expect(open.classes()).toContain('button-compact')
  expect(wrapper.text()).not.toContain('Im Admin ansehen')
  expect(wrapper.get('time').text()).toBe(dateTime(first.created_at))
  wrapper.unmount()
})
