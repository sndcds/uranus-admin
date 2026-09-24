// @vitest-environment node
import { readFileSync } from 'node:fs'
import { expect, it } from 'vitest'

// This is intentionally scoped to entity presentation, not workflow labels or source content.
it.each([
  'ActivityRow',
  'EntityCollectionRow',
  'EntityDetailPage',
  'EntityHero',
  'RecordRelations',
])('%s does not reintroduce legacy wording for internal record navigation', (component) => {
  const source = readFileSync(
    new URL(`../../app/components/${component}.vue`, import.meta.url),
    'utf8',
  )
  expect(source).not.toMatch(/Im Admin ansehen|Datensatz ansehen/)
  if (component === 'ActivityRow' || component === 'EntityCollectionRow') {
    expect(source).toMatch(/>Öffnen<\/NuxtLink\s*>/)
    expect(source).toContain('class="button button-compact"')
  }
})
