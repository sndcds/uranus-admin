<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ResearchSqlStatement } from '#shared/research-execution'
import SqlWorkspaceModal from './SqlWorkspaceModal.vue'
import SqlQueryPanel from './SqlQueryPanel.vue'

const props = defineProps<{ statements: ResearchSqlStatement[]; semantic: boolean }>()
const dialog = ref<InstanceType<typeof SqlWorkspaceModal> | null>(null)
const selected = ref(0)
const statement = computed(() => props.statements[selected.value])
function open() {
  selected.value = 0
  dialog.value?.open()
}
watch(
  () => props.statements,
  () => {
    dialog.value?.close()
    selected.value = 0
  },
)
defineExpose({ open })
</script>

<template>
  <SqlWorkspaceModal
    ref="dialog"
    title="SQL Editor"
    subtitle="Ausgeführte SQL-Abfragen dieser Recherche."
    close-label="SQL Editor schließen"
    @close="selected = 0"
  >
    <template #context>
      <section aria-label="Research-Datenquelle" class="space-y-2">
        <h3 class="font-semibold text-slate-950">Recherche · Uranus</h3>
        <p>Quelle: PostgreSQL · uranus</p>
        <p>Research-Quellzugriff · READ ONLY</p>
        <p class="text-xs text-slate-500">
          Standortwerte und Geometrien sind ausgeblendet. Kopiert wird ausschließlich
          parametrisiertes SQL.
        </p>
      </section>
    </template>
    <template v-if="statements.length > 1" #navigation>
      <button
        v-for="(item, index) in statements"
        :key="index"
        class="sql-nav"
        :aria-current="selected === index ? 'page' : undefined"
        @click="selected = index"
      >
        {{ item.label }}
      </button>
    </template>
    <p v-if="semantic" class="text-sm text-slate-600">
      Die semantische Rangfolge entsteht zwischen SQL-Vorauswahl und SQL-Rehydration im Vektorindex.
    </p>
    <SqlQueryPanel
      v-if="statement"
      :key="selected"
      :sql="statement.sql"
      :copy-sql="statement.sql"
      :description="statement.label"
      :parameters="statement.parameters"
      :executable="false"
      :running="false"
      error=""
      :result="null"
      hide-result
    />
  </SqlWorkspaceModal>
</template>
