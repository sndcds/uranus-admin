<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, shallowRef, watch } from 'vue'
import type { SqlToken } from '~/utils/sql-highlighter'

// This phase deliberately exposes no edit event or mutable SQL model.
const props = defineProps<{ sql: string; readonly?: true }>()
const tokens = shallowRef<SqlToken[]>([])
const highlightedSql = shallowRef<string | null>(null)
const displayedTokens = computed(() =>
  highlightedSql.value === props.sql ? tokens.value : [{ text: props.sql, type: '' }],
)
const lineCount = computed(() => props.sql.split('\n').length)
let revision = 0
async function highlight() {
  const current = ++revision
  const sql = props.sql
  try {
    const { highlightSql } = await import('~/utils/sql-highlighter')
    const result = highlightSql(sql)
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
    class="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950 text-slate-100"
    tabindex="0"
    role="region"
    aria-label="SQL-Abfrage, Nur-Lese-Modus"
  >
    <div class="flex min-w-max py-4 font-mono text-xs leading-6 sm:text-sm">
      <div
        aria-hidden="true"
        class="select-none border-r border-slate-800 px-4 text-right text-slate-500"
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
