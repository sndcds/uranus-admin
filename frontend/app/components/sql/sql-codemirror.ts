import { EditorState, StateEffect, StateField } from '@codemirror/state'
import { Decoration, EditorView, keymap, lineNumbers, drawSelection } from '@codemirror/view'
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands'
import { highlightSql } from '~/utils/sql-highlighter'

// The same Prism grammar and CSS classes as SqlReadonlyCode. No competing lexer/theme.
export function sqlDecorations(state: EditorState) {
  let offset = 0
  const ranges = []
  for (const token of highlightSql(state.doc.toString())) {
    if (token.type && token.text.length)
      ranges.push(
        Decoration.mark({ class: `token ${token.type}` }).range(offset, offset + token.text.length),
      )
    offset += token.text.length
  }
  return Decoration.set(ranges)
}
const highlighting = StateField.define({
  create: sqlDecorations,
  update: (value, transaction) =>
    transaction.docChanged ? sqlDecorations(transaction.state) : value,
  provide: (field) => EditorView.decorations.from(field),
})
export const errorPosition = StateEffect.define<number | null>()
const errors = StateField.define({
  create: () => Decoration.none,
  update(value, transaction) {
    if (transaction.docChanged) return Decoration.none
    for (const effect of transaction.effects) {
      if (effect.is(errorPosition)) {
        const position = effect.value
        if (position === null || !transaction.state.doc.length) return Decoration.none
        const from = Math.min(Math.max(0, position - 1), transaction.state.doc.length - 1)
        return Decoration.set([
          Decoration.mark({ class: 'sql-error-position' }).range(from, from + 1),
        ])
      }
    }
    return value
  },
  provide: (field) => EditorView.decorations.from(field),
})
// Layout adapter only. Every visual value comes from the existing shared SQL panel.
export const sqlCodeMirrorTheme = EditorView.theme({
  '&': {
    backgroundColor: 'var(--sql-background)',
    color: 'var(--sql-foreground)',
    minHeight: 'inherit',
  },
  '&.cm-focused': { outline: 'none' },
  '.cm-scroller': {
    fontFamily: 'var(--sql-font)',
    fontSize: 'var(--sql-font-size)',
    lineHeight: 'var(--sql-line-height)',
    fontWeight: 'var(--sql-font-weight)',
    letterSpacing: 'var(--sql-letter-spacing)',
    overflow: 'visible',
  },
  '.cm-content': {
    padding: 'var(--sql-padding-y) 20px var(--sql-padding-y) 0',
    caretColor: 'var(--sql-cursor)',
  },
  '.cm-line': { padding: '0 var(--sql-padding-x)', overflowWrap: 'normal', wordBreak: 'normal' },
  '.cm-gutters': {
    backgroundColor: 'var(--sql-background)',
    color: 'var(--sql-line-number)',
    borderRight: '1px solid var(--sql-gutter-border)',
  },
  '.cm-lineNumbers .cm-gutterElement': { padding: '0 var(--sql-gutter-padding)', minWidth: '0' },
  '.cm-cursor': { borderLeftColor: 'var(--sql-cursor)' },
  '.cm-activeLine': { backgroundColor: 'var(--sql-active-line)' },
  '&.cm-focused .cm-selectionBackground, .cm-selectionBackground': {
    background: 'var(--sql-selection)',
  },
})
export function createSqlEditor(
  parent: HTMLElement,
  sql: string,
  onChange: (sql: string) => void,
  execute: () => void,
  format: () => void,
) {
  return new EditorView({
    parent,
    state: EditorState.create({
      doc: sql,
      extensions: [
        sqlCodeMirrorTheme,
        highlighting,
        errors,
        lineNumbers(),
        drawSelection(),
        EditorView.lineWrapping,
        history(),
        EditorState.tabSize.of(4),
        EditorView.contentAttributes.of({
          'aria-label': 'SQL-Abfrage bearbeiten',
          spellcheck: 'false',
        }),
        keymap.of([
          {
            key: 'Mod-Enter',
            run: () => {
              execute()
              return true
            },
          },
          {
            key: 'Alt-Shift-f',
            run: () => {
              format()
              return true
            },
          },
          indentWithTab,
          ...defaultKeymap,
          ...historyKeymap,
        ]),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) onChange(update.state.doc.toString())
        }),
        EditorState.changeFilter.of((transaction) => transaction.newDoc.length <= 32768),
      ],
    }),
  })
}
