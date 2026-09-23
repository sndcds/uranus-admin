import MarkdownIt, { type Token } from 'markdown-it'
import { h, type VNodeChild } from 'vue'

const parser = new MarkdownIt('commonmark', { html: false, linkify: false, maxNesting: 20 })
parser.disable(['image'])

/** Source content cannot choose relative admin navigation; accept explicit external protocols only. */
export function markdownLink(value: string): { href: string; external: boolean } | null {
  if (
    /[\s\\]/u.test(value) ||
    [...value].some((char) => char.charCodeAt(0) < 32 || char.charCodeAt(0) === 127) ||
    /%(?:0[0-9a-f]|1[0-9a-f]|7f)/i.test(value)
  )
    return null
  try {
    // No base URL: root-, path-, query- and fragment-relative links are all rejected.
    const url = new URL(value)
    if (url.username || url.password) return null
    if (['http:', 'https:'].includes(url.protocol) && url.hostname)
      return { href: url.href, external: true }
    if (
      url.protocol === 'mailto:' &&
      !url.hash &&
      !url.search &&
      /^mailto:[^@?]+@[^@?]+$/i.test(value)
    )
      return { href: url.href, external: true }
  } catch {
    /* Untrusted links remain ordinary text. */
  }
  return null
}

const tags: Record<string, string> = {
  paragraph_open: 'p',
  strong_open: 'strong',
  em_open: 'em',
  bullet_list_open: 'ul',
  ordered_list_open: 'ol',
  list_item_open: 'li',
  blockquote_open: 'blockquote',
}
type Frame = { tag: string | null; props: Record<string, unknown>; children: VNodeChild[] }
function renderTokens(tokens: Token[], headingOffset = 3): VNodeChild[] {
  const root: Frame = { tag: null, props: {}, children: [] }
  const stack = [root]
  for (const token of tokens) {
    const frame = stack.at(-1)!
    if (token.nesting === -1) {
      if (stack.length === 1) continue
      const completed = stack.pop()!
      if (completed.props.target === '_blank') {
        completed.children.push(h('span', { 'aria-hidden': 'true' }, ' ↗︎'))
        completed.children.push(h('span', { class: 'sr-only' }, ' (neuer Tab)'))
      }
      if (completed.tag)
        stack.at(-1)!.children.push(h(completed.tag, completed.props, completed.children))
      else stack.at(-1)!.children.push(...completed.children)
    } else if (token.nesting === 1) {
      let tag: string | null = token.hidden ? null : (tags[token.type] ?? null)
      let props: Record<string, unknown> = {}
      if (token.type === 'heading_open' && /^h[1-6]$/.test(token.tag))
        tag = `h${Math.min(6, Number(token.tag[1]) + headingOffset)}`
      if (token.type === 'ordered_list_open') {
        const startValue = token.attrGet('start')
        const start = Number(startValue)
        if (startValue !== null && Number.isSafeInteger(start) && start >= 0) props.start = start
      }
      if (token.type === 'link_open') {
        const link = markdownLink(String(token.attrGet('href') ?? ''))
        if (link) {
          tag = 'a'
          props = { href: link.href }
          if (link.external)
            props = {
              ...props,
              target: '_blank',
              rel: 'noopener noreferrer',
              referrerpolicy: 'no-referrer',
            }
        }
      }
      stack.push({ tag, props, children: [] })
    } else if (token.type === 'inline') frame.children.push(...renderTokens(token.children ?? []))
    else if (token.type === 'softbreak') frame.children.push(' ')
    else if (token.type === 'hardbreak') frame.children.push(h('br'))
    else if (token.type === 'code_inline') frame.children.push(h('code', token.content))
    else if (['fence', 'code_block'].includes(token.type))
      frame.children.push(
        h('pre', { tabindex: 0, role: 'region', 'aria-label': 'Codeblock' }, [
          h('code', token.content),
        ]),
      )
    else frame.children.push(token.content)
  }
  return root.children
}

/** A parser is not an HTML sanitizer: only this closed token-to-Vue mapping owns elements. */
export function markdownNodes(source: string): VNodeChild[] {
  if (source.length > 100_000) return [h('p', { class: 'prose-admin-plain' }, source)]
  try {
    const tokens = parser.parse(source, {})
    const levels = tokens
      .filter((token) => token.type === 'heading_open')
      .map((token) => Number(token.tag[1]))
    return renderTokens(tokens, 4 - Math.min(...levels, 6))
  } catch {
    return [h('p', { class: 'prose-admin-plain' }, source)]
  }
}
