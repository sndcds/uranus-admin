import { expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import MarkdownContent from '../../app/components/MarkdownContent.vue'
import { markdownLink } from '../../app/utils/markdown'

it('renders the supported Markdown subset as semantic Vue nodes below the section heading', () => {
  const wrapper = mount(MarkdownContent, {
    props: {
      source:
        '# Heading\n\nText **strong** and *emphasis*, `inline`.\nline  \nbreak\n\n- one\n- two\n\n3. third\n4. fourth\n\n> quote\n\n```html\n<script>alert(1)</script>\n```',
    },
  })
  expect(wrapper.get('h4').text()).toBe('Heading')
  expect(wrapper.find('h1, h2, h3').exists()).toBe(false)
  expect(wrapper.get('strong').text()).toBe('strong')
  expect(wrapper.get('em').text()).toBe('emphasis')
  expect(wrapper.findAll('ul li')).toHaveLength(2)
  expect(wrapper.get('ol').attributes('start')).toBe('3')
  expect(wrapper.get('blockquote').text()).toContain('quote')
  expect(wrapper.findAll('br')).toHaveLength(1)
  expect(wrapper.get('pre code').text()).toContain('<script>alert(1)</script>')
  expect(wrapper.find('script').exists()).toBe(false)
})
it('renders a CommonMark softbreak as normal flowing whitespace', () => {
  const wrapper = mount(MarkdownContent, { props: { source: 'Zeile eins\nZeile zwei' } })
  expect(wrapper.find('br').exists()).toBe(false)
  expect(wrapper.get('p').text()).toBe('Zeile eins Zeile zwei')
})
it('renders a CommonMark hardbreak as one visible line break', () => {
  const wrapper = mount(MarkdownContent, { props: { source: 'Zeile eins  \nZeile zwei' } })
  expect(wrapper.findAll('br')).toHaveLength(1)
})
it('keeps paragraph breaks as separate paragraphs', () => {
  const wrapper = mount(MarkdownContent, { props: { source: 'Absatz eins\n\nAbsatz zwei' } })
  expect(wrapper.findAll('p').map((paragraph) => paragraph.text())).toEqual([
    'Absatz eins',
    'Absatz zwei',
  ])
  expect(wrapper.find('br').exists()).toBe(false)
})
it('does not create source HTML, images, handlers or dangerous links', () => {
  const source =
    '<img src=x onerror=alert(1)>\n\n<script>alert(1)</script>\n\n![tracking](https://example.org/pixel)\n\n[x](javascript:alert%281%29) [x](data:text/html,hello) [x](vbscript:evil) [x](//evil.example/x)'
  const wrapper = mount(MarkdownContent, { props: { source } })
  expect(wrapper.find('img, script, iframe, style, [onerror]').exists()).toBe(false)
  expect(wrapper.text()).toContain('<img src=x onerror=alert(1)>')
  for (const link of wrapper.findAll('a')) expect(link.attributes('href')).toMatch(/^https:\/\//)
})
it.each([
  'javascript:alert(1)',
  'JaVaScRiPt:alert(1)',
  'data:text/html,x',
  'vbscript:x',
  '//evil.example',
  '/\\evil.example',
  '/api/admin/auth/logout',
  '/login',
  '/unknown',
  '/events%2f..%2flogin',
  'https://user:secret@example.org',
  'https://example.org/%0afoo',
  'java\nscript:alert(1)',
  'mailto:a@example.org?body=secret',
  'mailto:a@example.org#fragment',
])('rejects unsafe or unapproved link %s', (value) => expect(markdownLink(value)).toBeNull())
it.each(['https://example.org/a', 'http://example.org', 'mailto:a@example.org'])(
  'accepts explicitly allowed link %s',
  (value) => expect(markdownLink(value)).not.toBeNull(),
)
it.each([
  '/sql',
  '/findings',
  '/queues/team_invitations',
  '/notifications',
  '/marks',
  '/checks',
  '/inbox',
  '/events',
  '/events/20000000-0000-4000-8000-000000000001',
  '/organizations/20000000-0000-4000-8000-000000000001',
  '/venues/20000000-0000-4000-8000-000000000001',
  '/spaces/20000000-0000-4000-8000-000000000001',
  '/users/20000000-0000-4000-8000-000000000001',
  '/images/20000000-0000-4000-8000-000000000001',
  '/findings?mode=persisted',
  'relative-path',
  '../sql',
  '?mode=persisted',
  '#details',
])('keeps source-authored relative link %s as text, never admin navigation', (href) => {
  expect(markdownLink(href)).toBeNull()
  const wrapper = mount(MarkdownContent, { props: { source: `[Source label](${href})` } })
  expect(wrapper.find('a').exists()).toBe(false)
  expect(wrapper.text()).toBe('Source label')
})
it.each(['https://example.org', 'http://example.org', 'mailto:a@example.org'])(
  'retains external link protections and the accessible new-tab hint for %s',
  (href) => {
    const wrapper = mount(MarkdownContent, {
      props: { source: `[Program](${href})` },
    })
    const links = wrapper.findAll('a')
    expect(links[0]!.attributes()).toMatchObject({
      target: '_blank',
      rel: 'noopener noreferrer',
      referrerpolicy: 'no-referrer',
    })
    expect(links[0]!.text()).toContain('neuer Tab')
  },
)
it('keeps oversized content fully readable as plain text and reacts to replacement', async () => {
  const source = '**x**'.repeat(21_000)
  const wrapper = mount(MarkdownContent, { props: { source } })
  expect(wrapper.text()).toBe(source)
  expect(wrapper.find('strong').exists()).toBe(false)
  await wrapper.setProps({ source: '**new**' })
  expect(wrapper.get('strong').text()).toBe('new')
})

it('normalizes a description starting at a deeper source heading without skipping the section level', () => {
  const wrapper = mount(MarkdownContent, { props: { source: '## First\n\n### Child' } })
  expect(wrapper.get('h4').text()).toBe('First')
  expect(wrapper.get('h5').text()).toBe('Child')
})

it('preserves a zero-start ordered list and normal default numbering', () => {
  const wrapper = mount(MarkdownContent, {
    props: { source: '0. Zero\n1. One\n\nText\n\n1. First' },
  })
  expect(wrapper.findAll('ol')[0]!.attributes('start')).toBe('0')
  expect(wrapper.findAll('ol')[1]!.attributes('start')).toBeUndefined()
})
