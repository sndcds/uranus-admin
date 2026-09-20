import Prism from 'prismjs/components/prism-core'
import 'prismjs/components/prism-json'
import type { SqlToken } from './sql-highlighter'
Prism.manual = true
export function highlightJson(json: string): SqlToken[] {
  function flatten(token: string | Prism.Token, type = ''): SqlToken[] {
    if (typeof token === 'string') return [{ text: token, type }]
    const parts = Array.isArray(token.content) ? token.content : [token.content]
    return parts.flatMap((part) => flatten(part, token.type))
  }
  return Prism.tokenize(json, Prism.languages.json!).flatMap((token) => flatten(token))
}
