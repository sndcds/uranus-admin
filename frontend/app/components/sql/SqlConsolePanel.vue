<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import SqlQueryPanel from './SqlQueryPanel.vue'
import { useSqlConsole } from '~/composables/useSqlConsole'
import { formatSql } from '~/utils/sql-format'
const props = withDefaults(
  defineProps<{
    sql: string
    parameters?: Record<string, string | number | boolean | null>
    page?: boolean
    finding?: boolean
  }>(),
  { parameters: () => ({}) },
)
const emit = defineEmits<{ busy: [value: boolean]; connection: [value: boolean] }>()
const rawSql = ref(props.sql),
  original = ref(props.sql),
  rowLimit = ref(50)
const session = useSqlConsole()
const { status, connected, busy, result, error, position } = session
const changed = computed(() => rawSql.value !== original.value)
onMounted(async () => {
  const formattedSql = await formatSql(props.sql)
  if (rawSql.value === props.sql) {
    rawSql.value = formattedSql
    original.value = formattedSql
  }
})
watch(busy, (value) => emit('busy', value))
watch(connected, (value) => emit('connection', value))
async function format() {
  if (busy.value) return
  const before = rawSql.value
  const formattedSql = await formatSql(before)
  if (rawSql.value === before) rawSql.value = formattedSql
}
function execute() {
  void session.execute(rawSql.value, rowLimit.value)
}
defineExpose({ cancel: session.cancel })
</script>
<template>
  <div class="space-y-4">
    <div
      v-if="finding"
      class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-950"
    >
      <p class="font-semibold">
        {{ changed ? 'Benutzerdefinierte Abfrage' : 'Console-Abfrage aus registrierter Diagnose' }}
      </p>
      <p>Die ursprüngliche Befundregel wird für diese geänderte Abfrage nicht ausgewertet.</p>
      <p>
        Startwerte wurden serverseitig eingesetzt. Zugriff ausschließlich auf freigegebene
        Console-Views.
      </p>
      <button v-if="changed" class="button mt-2" :disabled="busy" @click="rawSql = original">
        Original wiederherstellen
      </button>
    </div>
    <SqlQueryPanel
      :sql="rawSql"
      :copy-sql="rawSql"
      description="Uranus Console · READ ONLY · Ctrl/Cmd + Enter ausführen · Shift + Alt + F formatieren"
      :parameters="parameters"
      executable
      :running="busy"
      :error="error"
      :result="result"
      editable
      :page="page"
      :error-position="position"
      :status="status"
      @update:sql="rawSql = $event"
      @execute="execute"
      @cancel="session.cancel"
      @format="format"
    >
      <template #actions
        ><label class="flex items-center gap-2 text-xs"
          >Zeilen<select
            v-model.number="rowLimit"
            class="rounded border border-slate-200 p-1"
            :disabled="busy"
            aria-label="Zeilenlimit"
          >
            <option :value="50">50</option>
            <option :value="100">100</option>
            <option :value="500">500</option>
          </select></label
        ></template
      >
    </SqlQueryPanel>
  </div>
</template>
