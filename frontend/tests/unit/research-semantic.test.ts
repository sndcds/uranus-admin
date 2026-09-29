import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { computed } from 'vue'
import { researchPageSchema, semanticResearchPageSchema } from '../../shared/contracts'
import { createAdminApi } from '../../app/utils/admin-api'
import ResearchResult from '../../app/components/ResearchResult.vue'
import ResearchSemanticExplanation from '../../app/components/ResearchSemanticExplanation.vue'
import {
  researchEvent,
  researchPage,
  semanticResearchEvent,
  semanticResearchPage,
} from '../fixtures/research'

afterEach(() => vi.unstubAllGlobals())

describe('semantic evidence contracts', () => {
  it('requires evidence and keeps classic records separate', () => {
    expect(semanticResearchPageSchema.parse(semanticResearchPage())).toEqual(semanticResearchPage())
    expect(semanticResearchPageSchema.safeParse(researchPage()).success).toBe(false)
    expect(researchPageSchema.safeParse(semanticResearchPage()).success).toBe(false)
  })
  it.each(['email', 'contact', 'internal_notes', 'payload', 'score'])(
    'rejects unknown evidence field %s',
    (field) => {
      const page = semanticResearchPage()
      const item = page.items[0]!
      for (const target of ['evidence', 'supporting_evidence'] as const) {
        const evidence = { ...item.semantic.evidence, [field]: 'private' }
        const semantic = {
          ...item.semantic,
          [target]: target === 'evidence' ? evidence : [evidence],
        }
        expect(
          semanticResearchPageSchema.safeParse({ ...page, items: [{ ...item, semantic }] }).success,
        ).toBe(false)
      }
    },
  )
  it('bounds evidence kinds, text, supporting chunks, records and finite scores', () => {
    const page = semanticResearchPage()
    const item = page.items[0]!
    for (const change of [
      { evidence: { ...item.semantic.evidence, kind: 'internal' } },
      { evidence: { ...item.semantic.evidence, text: '' } },
      { evidence: { ...item.semantic.evidence, text: 'x'.repeat(200001) } },
      { supporting_evidence: Array(4).fill(item.semantic.evidence) },
      { score: Infinity },
      { score: NaN },
      { extra: 'private' },
    ])
      expect(
        semanticResearchPageSchema.safeParse({
          ...page,
          items: [{ ...item, semantic: { ...item.semantic, ...change } }],
        }).success,
      ).toBe(false)
    expect(
      semanticResearchPageSchema.safeParse({ ...page, items: Array(21).fill(item) }).success,
    ).toBe(false)
  })
  it('API client parses and preserves evidence and rejects classic responses', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(semanticResearchPage())))
    expect(await createAdminApi(fetcher).researchSemanticSearch({ q: 'creative' })).toEqual(
      semanticResearchPage(),
    )
    fetcher.mockResolvedValue(new Response(JSON.stringify(researchPage())))
    await expect(
      createAdminApi(fetcher).researchSemanticSearch({ q: 'creative' }),
    ).rejects.toThrow()
  })
})

function render(semantic: boolean, item = semanticResearchEvent) {
  vi.stubGlobal('computed', computed)
  return mount(ResearchResult, {
    props: { item, semantic },
    global: {
      components: { ResearchSemanticExplanation },
      stubs: { NuxtLink: { template: '<a><slot /></a>' }, AppIcon: true, ResearchBadges: true },
    },
  })
}

it('shows the explanation only in semantic mode and preserves the classic renderer', async () => {
  const view = render(false)
  expect(view.text()).toContain(researchEvent.name)
  expect(view.text()).not.toContain('Warum passt das?')
  expect(view.find('details').exists()).toBe(false)
  await view.setProps({ semantic: true })
  expect(view.text()).toContain('Warum passt das?')
  expect(view.text()).toContain('Der Inhalt passt zur Suchanfrage.')
  expect(view.text()).toContain('Ähnlichkeit: 0.446')
  expect(view.text()).not.toContain('%')
  expect(view.get('details').attributes('open')).toBeUndefined()
  expect(view.get('summary').text()).toBe('Beleg anzeigen')
  expect(view.get('blockquote').text()).toContain(semanticResearchEvent.semantic.evidence.text)
  expect(view.text()).toContain('Weitere passende Bereiche')
  expect(view.text()).toContain(semanticResearchEvent.semantic.supporting_evidence[0]!.text)
  await view.setProps({ item: researchEvent })
  expect(view.text()).not.toContain('Warum passt das?')
  view.unmount()
})

it('renders evidence as wrapping plain text without executing HTML', () => {
  const explanation = {
    ...semanticResearchEvent.semantic,
    evidence: {
      ...semanticResearchEvent.semantic.evidence,
      text: '<img src=x onerror="alert(1)">',
    },
    supporting_evidence: [],
  }
  const view = mount(ResearchSemanticExplanation, { props: { explanation } })
  expect(view.find('img').exists()).toBe(false)
  expect(view.get('blockquote').text()).toContain('<img src=x')
  expect(view.get('blockquote').classes()).toContain('whitespace-pre-wrap')
  expect(view.text()).not.toContain('Weitere passende Bereiche')
  view.unmount()
})
