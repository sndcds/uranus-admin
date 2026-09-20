<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, shallowRef, watch } from 'vue'
import { formatSql } from '~/utils/sql-format'
import type { SqlToken } from '~/utils/sql-highlighter'

// This phase deliberately exposes no edit event or mutable SQL model.
const props = defineProps<{ sql: string; readonly?: true }>()
const tokens = shallowRef<SqlToken[]>([])
const highlightedSql = shallowRef<string | null>(null)
const displayedTokens = computed(() =>
  highlightedSql.value === props.sql ? tokens.value : [{ text: props.sql, type: '' }],
)
const lineCount = computed(
  () =>
    displayedTokens.value
      .map((token) => token.text)
      .join('')
      .split('\n').length,
)
let revision = 0
async function highlight() {
  const current = ++revision
  const sql = props.sql
  try {
    const formatted = await formatSql(sql)
    if (current !== revision) return
    tokens.value = [{ text: formatted, type: '' }]
    highlightedSql.value = sql
    const { highlightSql } = await import('~/utils/sql-highlighter')
    const result = highlightSql(formatted)
    if (current === revision) {
      tokens.value = result
      highlightedSql.value = sql
    }
  } catch {
    // Preserve readable plain SQL if the optional highlighting chunk cannot load.
  }
}
onMounted(() => {
  void highlight()
  watch(() => props.sql, highlight)
})
onBeforeUnmount(() => revision++)
</script>

<template>
  <div
    class="relative min-h-64 max-h-96 overflow-auto rounded-lg border border-slate-800 bg-slate-900 text-slate-100"
    :spellcheck="false"
    tabindex="0"
    role="region"
    aria-label="SQL-Abfrage, Nur-Lese-Modus"
  >
    <div class="sticky top-0 right-0 h-0 text-right" aria-hidden="true">
      <span
        class="mr-2 mt-2 inline-block rounded border border-slate-600 bg-slate-800 px-2 py-1 text-[10px] text-slate-200"
        >SQL (PostgreSQL)</span
      >
    </div>
    <div class="flex min-w-max py-3 pr-5 font-mono text-xs leading-5">
      <div
        aria-hidden="true"
        class="select-none border-r border-slate-700 px-3 text-right text-slate-400"
      >
        <div v-for="line in lineCount" :key="line">{{ line }}</div>
      </div>
      <pre
        class="m-0 px-4 font-inherit leading-inherit"
      ><code class="language-sql"><span v-for="(token, index) in displayedTokens" :key="index" :class="token.type ? `token ${token.type}` : undefined">{{ token.text }}</span></code></pre>
    </div>
  </div>
</template>

<style scoped>
.token.keyword {
  color: #f0abfc;
}
.token.string {
  color: #a7f3d0;
}
.token.number,
.token.boolean {
  color: #7dd3fc;
}
.token.parameter,
.token.variable {
  color: #c4b5fd;
}
.token.comment {
  color: #94a3b8;
}
.token.operator,
.token.punctuation {
  color: #cbd5e1;
}
.token.function {
  color: #fde68a;
}
</style>
