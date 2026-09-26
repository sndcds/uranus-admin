import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ResearchCategoryBadge from '../../app/components/ResearchCategoryBadge.vue'
import { researchCategoryColor } from '../../app/utils/research-categories'

describe('canonical Research category colors', () => {
  it.each([
    [1, 'culture', '#F20D5E'],
    [2, 'education', '#FF7A53'],
    [3, 'sports', '#F3B52A'],
    [4, 'leisure', '#04C18D'],
    [5, 'family', '#09BAEC'],
    [6, 'society', '#1A71E4'],
  ])('maps stable ID %s and key %s to %s', (id, key, color) => {
    expect(researchCategoryColor(id)).toBe(color)
    expect(researchCategoryColor(key)).toBe(color)
  })

  it.each([0, 7, 772, -1, NaN, 'unknown', 'constructor', '__proto__'])(
    'keeps unknown category %s neutral',
    (category) => expect(researchCategoryColor(category)).toBe('#64748B'),
  )

  it('keeps color independent of translated label and rendering order', async () => {
    const badge = mount(ResearchCategoryBadge, {
      props: { category: { id: 1, name: 'Culture' } },
    })
    const dot = () => badge.get('[aria-hidden="true"]').attributes('style')
    expect(dot()).toContain('#F20D5E')
    await badge.setProps({ category: { id: 5, name: 'Familie' } })
    expect(dot()).toContain('#09BAEC')
    for (const name of ['Kultur', 'Culture', 'Kultur (da)']) {
      await badge.setProps({ category: { id: 1, name } })
      expect(badge.text()).toBe(name)
      expect(dot()).toContain('#F20D5E')
    }
    await badge.setProps({ category: { id: 772, name: 'Kultur' } })
    expect(dot()).toContain('#64748B')
    badge.unmount()
  })
})
