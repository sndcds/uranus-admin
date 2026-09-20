<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, shallowRef, watch } from 'vue'
import type { SqlToken } from '~/utils/sql-highlighter'
const props = defineProps<{ rows: Record<string, unknown>[] }>()
const json = computed(() => JSON.stringify(props.rows, null, 2))
const tokens = shallowRef<SqlToken[]>([])
const highlighted = shallowRef('')
const displayed = computed(() =>
  highlighted.value === json.value ? tokens.value : [{ text: json.value, type: '' }],
)
let revision = 0
async function highlight() {
  const current = ++revision,
    text = json.value
  try {
    const { highlightJson } = await import('~/utils/json-highlighter')
    if (current !== revision) return
    tokens.value = highlightJson(text)
    highlighted.value = text
  } catch {
    /* Plain JSON remains readable if the optional chunk fails. */
  }
}
onMounted(() => {
  void highlight()
  watch(json, highlight)
})
onBeforeUnmount(() => revision++)
</script>
<template>
  <pre
    class="max-h-80 overflow-auto rounded-lg bg-slate-900 p-4 font-mono text-xs leading-5 text-slate-100"
    tabindex="0"
    role="region"
    aria-label="JSON-Ergebnis"
  ><code class="language-json"><span v-for="(token, index) in displayed" :key="index" :class="token.type">{{ token.text }}</span></code></pre>
</template>
<style scoped>
.property {
  color: #f0abfc;
}
.string {
  color: #a7f3d0;
}
.number,
.boolean {
  color: #7dd3fc;
}
.null {
  color: #c4b5fd;
}
</style>
