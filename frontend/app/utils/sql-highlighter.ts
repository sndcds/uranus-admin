import Prism from 'prismjs/components/prism-core'
import 'prismjs/components/prism-sql'

// Vue owns the DOM; disable Prism's scheduled automatic highlightAll callback.
Prism.manual = true

// Only SQL grammar. Named binds are SQLAlchemy's display syntax, not editable inputs.
const grammar = Prism.languages.insertBefore('sql', 'variable', {
  parameter: { pattern: /(^|[^:]):[a-z_]\w*/i, lookbehind: true },
})
export interface SqlToken {
  text: string
  type: string
}
export function highlightSql(sql: string): SqlToken[] {
  function flatten(token: string | Prism.Token, type = ''): SqlToken[] {
    if (typeof token === 'string') return [{ text: token, type }]
    const content = Array.isArray(token.content) ? token.content : [token.content]
    return content.flatMap((part) => flatten(part, token.type))
  }
  return Prism.tokenize(sql, grammar).flatMap((token) => flatten(token))
}
