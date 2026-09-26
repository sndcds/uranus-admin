// Canonical Kulturbytes category colors from sndcds/kulturbytes-client/app/assets/css/event.scss.
export const researchCategoryColors = {
  culture: '#F20D5E',
  education: '#FF7A53',
  sports: '#F3B52A',
  leisure: '#04C18D',
  family: '#09BAEC',
  society: '#1A71E4',
} as const

// Stable IDs from kulturbytes-client/app/components/event/ui/CategorySelector.vue.
const categoryKeys: Record<number, keyof typeof researchCategoryColors> = {
  1: 'culture',
  2: 'education',
  3: 'sports',
  4: 'leisure',
  5: 'family',
  6: 'society',
}

export function researchCategoryColor(category: number | string) {
  const key = typeof category === 'number' ? categoryKeys[category] : category
  return key && Object.hasOwn(researchCategoryColors, key)
    ? researchCategoryColors[key as keyof typeof researchCategoryColors]
    : '#64748B'
}
