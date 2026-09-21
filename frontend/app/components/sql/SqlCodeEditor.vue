<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import type { EditorView } from '@codemirror/view'
import SqlReadonlyCode from './SqlReadonlyCode.vue'
import './sql-theme.css'
const props = withDefaults(
  defineProps<{ sql: string; readonly?: boolean; page?: boolean; errorPosition?: number | null }>(),
  { readonly: true, errorPosition: null },
)
const emit = defineEmits<{ 'update:sql': [value: string]; execute: []; format: [] }>()
const host = ref<HTMLElement | null>(null)
const failed = ref(false)
let editor: EditorView | undefined
let disposed = false
onMounted(async () => {
  if (props.readonly) return
  try {
    const module = await import('./sql-codemirror')
    if (disposed || !host.value) return
    editor = module.createSqlEditor(
      host.value,
      props.sql,
      (value) => emit('update:sql', value),
      () => emit('execute'),
      () => emit('format'),
    )
    watch(
      () => props.errorPosition,
      (position) => {
        editor?.dispatch({ effects: module.errorPosition.of(position) })
        if (position && editor) {
          editor.dispatch({
            selection: { anchor: Math.min(position - 1, editor.state.doc.length) },
            scrollIntoView: true,
          })
          editor.focus()
        }
      },
    )
  } catch {
    failed.value = true
  }
})
watch(
  () => props.sql,
  (value) => {
    if (!editor || value === editor.state.doc.toString()) return
    const selection = editor.state.selection.main
    editor.dispatch({
      changes: { from: 0, to: editor.state.doc.length, insert: value },
      selection: {
        anchor: Math.min(selection.anchor, value.length),
        head: Math.min(selection.head, value.length),
      },
    })
  },
)
onBeforeUnmount(() => {
  disposed = true
  editor?.destroy()
})
defineExpose({ focus: () => editor?.focus() })
</script>
<template>
  <SqlReadonlyCode v-if="readonly" :sql="sql" />
  <div
    v-else
    ref="host"
    class="sql-code"
    :class="{ 'sql-page-editor': page }"
    role="region"
    aria-label="SQL-Abfrage, Bearbeitungsmodus"
  >
    <div class="sticky top-0 right-0 z-10 h-0 text-right pointer-events-none" aria-hidden="true">
      <span
        class="mr-2 mt-2 inline-block rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[10px] text-slate-200"
        >SQL (PostgreSQL)</span
      >
    </div>
    <p v-if="failed" role="alert">SQL Editor konnte nicht geladen werden. Bitte Seite neu laden.</p>
  </div>
</template>
