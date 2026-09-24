<script setup lang="ts">
import VenueScopeBadge from './VenueScopeBadge.vue'
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
const showLabels = defineModel<boolean>('showLabels', { default: true })
const depth = defineModel<number>('depth', { required: true })
defineProps<{
  results: GraphNode[]
  searching: boolean
  searched: boolean
  organizations: GraphNode[]
  loading: boolean
  hasRoot: boolean
  settingsOpen?: boolean
  geoActive?: boolean
}>()
defineEmits<{ select: [node: GraphNode]; apply: []; reset: []; settings: [] }>()
</script>
<template>
  <form
    class="operations-workspace-toolbar graph-filter-toolbar"
    aria-label="Graphfilter"
    @submit.prevent="$emit('apply')"
  >
    <div class="relative min-w-0 graph-search-field">
      <label for="graph-root-search" class="label">Root suchen</label>
      <div class="relative">
        <AppIcon
          name="search"
          :size="16"
          class="pointer-events-none absolute left-3 top-3 text-slate-400"
        />
        <input
          id="graph-root-search"
          v-model="query"
          :disabled="!ready"
          class="input pl-9"
          aria-label="Nach Name, E-Mail oder UUID suchen"
          placeholder="Nach Name, E-Mail oder UUID suchen …"
          maxlength="120"
          autocomplete="off"
          aria-controls="graph-search-results"
          @keydown.esc="query = ''"
        />
      </div>
      <div
        v-if="query.trim().length >= 2"
        id="graph-search-results"
        class="absolute left-0 top-full z-20 mt-2 max-h-80 w-full overflow-auto rounded-xl border border-slate-200 bg-white p-1 shadow-lg"
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
                ><span class="text-xs text-slate-500">{{ nodePresentation[node.type].label }}</span>
                <VenueScopeBadge
                  v-if="node.type === 'venue' && node.venue_scope"
                  :scope="node.venue_scope"
                />
              </span>
            </button>
          </li>
        </ul>
      </div>
    </div>
    <div class="min-w-0">
      <label for="graph-entity-type" class="label">Objektart</label>
      <select id="graph-entity-type" v-model="entityType" class="input" aria-label="Entitätstypen">
        <option value="">Alle Entitätstypen</option>
        <option
          v-for="(item, type) in nodePresentation"
          :key="type"
          :value="type"
          :disabled="geoActive && type === 'user'"
        >
          {{ item.label }}
        </option>
      </select>
    </div>
    <div class="min-w-0">
      <label for="graph-relation-type" class="label">Beziehung</label>
      <select
        id="graph-relation-type"
        v-model="relationType"
        class="input"
        aria-label="Beziehungstypen"
      >
        <option value="">Alle Beziehungen</option>
        <option v-for="(label, type) in relationLabels" :key="type" :value="type">
          {{ label }}
        </option>
      </select>
    </div>
    <div class="min-w-0">
      <label for="graph-depth" class="label">Tiefe</label>
      <select id="graph-depth" v-model.number="depth" class="input" aria-label="Maximale Tiefe">
        <option v-for="n in 3" :key="n" :value="n">
          {{ n }} {{ n === 1 ? 'Ebene' : 'Ebenen' }}
        </option>
      </select>
    </div>
    <div class="graph-filter-secondary">
      <div class="graph-organization">
        <label for="graph-organization" class="text-xs text-slate-600">Suchkontext</label>
        <select
          id="graph-organization"
          v-model="organization"
          class="input"
          aria-label="Organisation für Suche"
        >
          <option value="">Alle Organisationen</option>
          <option
            v-if="organization && !organizations.some((node) => node.key === organization)"
            :value="organization"
          >
            Gespeicherte Organisation
          </option>
          <option v-for="node in organizations" :key="node.id" :value="node.key">
            {{ node.label }}
          </option>
        </select>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button class="button-primary" :disabled="loading || !hasRoot">Anwenden</button>
        <button type="button" class="button" @click="$emit('reset')">Zurücksetzen</button>
        <button
          type="button"
          class="button button-compact"
          aria-controls="graph-display-settings"
          aria-label="Darstellung"
          :aria-expanded="settingsOpen"
          @click="$emit('settings')"
        >
          <AppIcon name="settings" :size="15" />Darstellung
        </button>
      </div>
    </div>
    <div
      v-if="settingsOpen"
      id="graph-display-settings"
      class="col-span-full border-t border-slate-200 pt-2"
    >
      <label class="flex min-h-11 items-center gap-2 text-sm">
        <input v-model="showLabels" type="checkbox" class="accent-fuchsia-700" />
        Beziehungen beschriften
      </label>
      <p class="text-xs text-slate-600">Bei dichten Graphen nur an der Auswahl.</p>
    </div>
  </form>
</template>

<style scoped>
.graph-filter-toolbar {
  display: grid;
  gap: 0.75rem;
  align-items: end;
}
.graph-filter-secondary {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  grid-column: 1 / -1;
  justify-content: space-between;
  align-items: center;
}
.graph-organization {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}
.graph-organization select {
  width: auto;
  max-width: 100%;
}
@media (min-width: 640px) {
  .graph-filter-toolbar {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .graph-search-field {
    grid-column: 1 / -1;
  }
}
@media (min-width: 1280px) {
  .graph-filter-toolbar {
    grid-template-columns: minmax(16rem, 2fr) minmax(0, 1fr) minmax(0, 1fr) 7.5rem;
  }
  .graph-search-field {
    grid-column: auto;
  }
}
</style>
