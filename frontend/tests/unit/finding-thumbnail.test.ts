import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ActivityThumbnail from '../../app/components/ActivityThumbnail.vue'
import { findingSchema } from '../../shared/contracts'
import { findings } from '../fixtures/api'

const image =
  'https://api.kulturbytes.de/api/image/00000000-0000-4000-8000-000000000060?width=320&type=png'
const item = { ...findings.items[0]!, entity_type: 'event_date', image_url: image }
const global = { stubs: { AppIcon: true } }

describe('compact finding images', () => {
  it('uses the existing safe thumbnail without a button or image modal', () => {
    const view = mount(ActivityThumbnail, { props: { item, compact: true }, global })
    expect(view.get('img').attributes()).toMatchObject({
      src: image,
      alt: item.entity_name,
      loading: 'lazy',
      crossorigin: 'anonymous',
      referrerpolicy: 'no-referrer',
    })
    expect(view.find('button').exists()).toBe(false)
    expect(view.find('dialog').exists()).toBe(false)
    view.unmount()
  })
  it('falls back on broken or missing images and resets for the next record', async () => {
    const view = mount(ActivityThumbnail, { props: { item, compact: true }, global })
    await view.get('img').trigger('error')
    expect(view.find('img').exists()).toBe(false)
    expect(view.get('app-icon-stub').attributes('name')).toBe('clock')
    await view.setProps({ item: { ...item, entity_key: 'different-record' } })
    expect(view.find('img').exists()).toBe(true)
    await view.setProps({ item: { ...item, entity_type: 'event_link', image_url: undefined } })
    expect(view.find('img').exists()).toBe(false)
    expect(view.get('app-icon-stub').attributes('name')).toBe('image')
    view.unmount()
  })
  it.each([
    'https://evil.invalid/image.png',
    'javascript:alert(1)',
    'https://user:pass@api.kulturbytes.de/api/image/00000000-0000-4000-8000-000000000060?width=320&type=png',
  ])('rejects unsafe image URL %s', (image_url) => {
    expect(findingSchema.safeParse({ ...item, image_url }).success).toBe(false)
    const view = mount(ActivityThumbnail, {
      props: { item: { ...item, image_url }, compact: true },
      global,
    })
    expect(view.find('img').exists()).toBe(false)
    view.unmount()
  })
  it('accepts older responses without an image and explicit absent images', () => {
    expect(findingSchema.safeParse(findings.items[0]).success).toBe(true)
    expect(findingSchema.safeParse({ ...item, image_url: null }).success).toBe(true)
  })
})
