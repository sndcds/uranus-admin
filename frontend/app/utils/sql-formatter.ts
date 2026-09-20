import { formatDialect, postgresql, type DialectOptions } from 'sql-formatter'

type Tokens = Parameters<NonNullable<DialectOptions['tokenizerOptions']['postProcess']>>[0]
let capture = (_tokens: Tokens): void => {}
// Reuse the library's cached PostgreSQL tokenizer, including dollar strings and nested comments.
const dialect: DialectOptions = {
  ...postgresql,
  tokenizerOptions: {
    ...postgresql.tokenizerOptions,
    postProcess(tokens) {
      capture(tokens)
      return tokens
    },
  },
  formatOptions: {
    ...postgresql.formatOptions,
    onelineClauses: [
      ...(postgresql.formatOptions.onelineClauses ?? []),
      'FROM',
      'WHERE',
      'GROUP BY',
      'HAVING',
      'ORDER BY',
      'OFFSET',
    ],
  },
}
const options = {
  dialect,
  tabWidth: 4,
  keywordCase: 'upper' as const,
  expressionWidth: 110,
  paramTypes: { named: [':' as const] },
}
function signature(tokens: Tokens) {
  return tokens.map((token) => [token.type, token.text])
}
export function formatPostgresql(sql: string): string {
  if (!sql.trim() || sql.length > 200_000) return sql
  let original: Tokens = [],
    rendered: Tokens = []
  try {
    capture = (tokens) => {
      original = tokens
    }
    // A separate line keeps a trailing line comment from swallowing the terminator.
    const input = sql.trimEnd().endsWith(';') ? sql : `${sql}\n;`
    const formatted = formatDialect(input, options)
    capture = (tokens) => {
      rendered = tokens
    }
    formatDialect(formatted, options)
    // Fail closed to the original presentation if the formatter changes tokens.
    if (JSON.stringify(signature(original)) !== JSON.stringify(signature(rendered))) return sql
    for (let i = 1; i < original.length; i++) {
      // PostgreSQL concatenates adjacent string literals only across a newline.
      if (
        original[i]?.type === 'STRING' &&
        original[i - 1]?.type === 'STRING' &&
        /\n/.test(original[i]?.precedingWhitespace ?? '') !==
          /\n/.test(rendered[i]?.precedingWhitespace ?? '')
      )
        return sql
    }
    // Whitespace-only layout adjustments at lexer-verified keyword boundaries.
    // Never search/replace SQL text inside strings, identifiers or comments.
    const edits: { start: number; end: number; text: string }[] = []
    for (const token of rendered) {
      const before = token.precedingWhitespace ?? ''
      const lineStart = formatted.lastIndexOf('\n', token.start - 1) + 1
      const indent = formatted.slice(lineStart).match(/^ */)?.[0] ?? ''
      if (token.type === 'LIMIT') {
        const end = token.start + token.raw.length
        const whitespace = formatted.slice(end).match(/^\s+/)?.[0]
        if (whitespace) edits.push({ start: end, end: end + whitespace.length, text: ' ' })
      }
      if (
        (token.type === 'RESERVED_KEYWORD' && token.text === 'ON') ||
        ((token.type === 'AND' || token.type === 'OR') && before.includes('\n'))
      ) {
        edits.push({
          start: token.start - before.length,
          end: token.start,
          text: `\n${indent}    `,
        })
      }
    }
    return edits
      .sort((a, b) => b.start - a.start)
      .reduce(
        (text, edit) => text.slice(0, edit.start) + edit.text + text.slice(edit.end),
        formatted,
      )
  } catch {
    return sql
  } finally {
    capture = () => {}
  }
}
