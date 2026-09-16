<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { GraphNode } from '#shared/contracts'
import { nodePresentation, relationLabels } from '~/utils/graph'
const ready = ref(false)
onMounted(() => {
  ready.value = true
})
const query = defineModel<string>('query', { required: true })
const entityType = defineModel<string>('entityType', { required: true })
const relationType = defineModel<string>('relationType', { required: true })
const organization = defineModel<string>('organization', { required: true })
const depth = defineModel<number>('depth', { required: true })
defineProps<{
  results: GraphNode[]
  searching: boolean
  searched: boolean
  organizations: GraphNode[]
  loading: boolean
  hasRoot: boolean
  settingsOpen?: boolean
}>()
defineEmits<{ select: [node: GraphNode]; apply: []; reset: []; settings: [] }>()
</script>
<template>
  <form
    class="graph-filters rounded-xl border border-slate-200 bg-white p-3"
    aria-label="Graphfilter"
    @submit.prevent="$emit('apply')"
  >
    <div class="relative min-w-0">
      <AppIcon
        name="search"
        :size="16"
        class="pointer-events-none absolute left-3 top-3 text-slate-400"
      />
      <input
        v-model="query"
        :disabled="!ready"
        class="input pl-9"
        aria-label="Nach Name oder UUID suchen"
        placeholder="Nach Name oder UUID suchen …"
        maxlength="120"
        autocomplete="off"
        aria-controls="graph-search-results"
        @keydown.esc="query = ''"
      />
      <div
        v-if="query.trim().length >= 2"
        id="graph-search-results"
        class="absolute left-0 top-full z-20 mt-2 max-h-80 w-full min-w-64 overflow-auto rounded-xl border border-slate-200 bg-white p-1 shadow-lg"
      >
        <p v-if="searching" class="p-3 text-xs text-slate-500" role="status">Suche läuft …</p>
        <p v-else-if="searched && !results.length" class="p-3 text-xs text-slate-500" role="status">
          Keine passenden Datensätze gefunden.
        </p>
        <ul aria-label="Suchergebnisse">
          <li v-for="node in results" :key="node.id">
            <button
              type="button"
              class="flex w-full items-center gap-3 rounded-lg p-3 text-left hover:bg-fuchsia-50"
              @click="$emit('select', node)"
            >
              <AppIcon
                :name="nodePresentation[node.type].icon"
                :style="{ color: nodePresentation[node.type].color }"
              />
              <span class="min-w-0"
                ><span class="block truncate text-sm font-medium">{{ node.label }}</span
                ><span class="text-xs text-slate-500">{{
                  nodePresentation[node.type].label
                }}</span></span
              >
            </button>
          </li>
        </ul>
      </div>
    </div>
    <select v-model="entityType" class="input" aria-label="Entitätstypen">
      <option value="">Alle Entitätstypen</option>
      <option v-for="(item, type) in nodePresentation" :key="type" :value="type">
        {{ item.label }}
      </option>
    </select>
    <select v-model="relationType" class="input" aria-label="Beziehungstypen">
      <option value="">Alle Beziehungen</option>
      <option v-for="(label, type) in relationLabels" :key="type" :value="type">{{ label }}</option>
    </select>
    <select v-model="organization" class="input" aria-label="Organisation für Suche">
      <option value="">Alle Organisationen</option>
      <option v-for="node in organizations" :key="node.id" :value="node.key">
        {{ node.label }}
      </option>
    </select>
    <select v-model.number="depth" class="input" aria-label="Maximale Tiefe">
      <option v-for="n in 3" :key="n" :value="n">
        Max. {{ n }} {{ n === 1 ? 'Ebene' : 'Ebenen' }}
      </option>
    </select>
    <button class="button-primary" :disabled="loading || !hasRoot">Anwenden</button>
    <button type="button" class="button" @click="$emit('reset')">Zurücksetzen</button>
    <button
      type="button"
      class="button !px-2.5"
      aria-label="Darstellung"
      :aria-expanded="settingsOpen"
      @click="$emit('settings')"
    >
      <AppIcon name="settings" :size="15" />
    </button>
  </form>
</template>
<style scoped>
.graph-filters {
  display: grid;
  grid-template-columns:
    minmax(200px, 1.5fr) repeat(3, minmax(115px, 1fr)) minmax(115px, 0.8fr)
    auto auto auto;
  gap: 10px;
  align-items: center;
}
.graph-filters :is(.input, .button, .button-primary) {
  font-size: 12px;
  border-radius: 8px;
  min-height: 38px;
}
@media (max-width: 1350px) {
  .graph-filters {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
  .graph-filters > :first-child {
    grid-column: span 2;
  }
}
@media (max-width: 640px) {
  .graph-filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
