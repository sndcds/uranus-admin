<script setup lang="ts">
import InlineAlert from '~/components/InlineAlert.vue'
import { computed, nextTick, ref, watch } from 'vue'
import type { GraphNode, GraphEdge, GraphResponse } from '#shared/contracts'
import type { ApiFailure } from '#shared/errors'
import { useFullscreen } from '~/composables/useFullscreen'
import { nodePresentation, relationLabels } from '~/utils/graph'
import AppIcon from './AppIcon.vue'
import EntityGraph from './EntityGraph.vue'
import GraphNodeDetails from './GraphNodeDetails.vue'
import RequestState from './RequestState.vue'
import TechnicalInfoBar from './TechnicalInfoBar.vue'
import type { TechnicalFact } from '~/utils/operations'
import { graphEntityTypeSchema, graphRelationTypeSchema } from '#shared/contracts'
const props = defineProps<{
  data: GraphResponse | null
  nodes: GraphNode[]
  edges: GraphEdge[]
  root: string
  selected: string
  depth: number
  showLabels: boolean
  loading: boolean
  error: ApiFailure | null
  entityFilter?: string
  relationFilter?: string
  geoScope?: string
}>()
const emit = defineEmits<{ select: [id: string]; root: [node: GraphNode]; retry: [] }>()
const fullscreenTarget = ref<HTMLElement | null>(null)
const graph = ref<InstanceType<typeof EntityGraph> | null>(null)
const {
  isFullscreen,
  isSupported,
  error: fullscreenError,
  toggleFullscreen,
} = useFullscreen(fullscreenTarget)
const detailsOpen = ref(true)
const selectedNode = computed(() => props.nodes.find((n) => n.id === props.selected))
const rootNode = computed(() => props.nodes.find((n) => n.id === props.root))
const technicalItems = computed<TechnicalFact[]>(() => {
  const entity = graphEntityTypeSchema.safeParse(props.entityFilter)
  const relation = graphRelationTypeSchema.safeParse(props.relationFilter)
  return [
    { label: 'Root', value: props.data ? props.root : null, mono: true },
    { label: 'Tiefe', value: props.depth },
    {
      label: 'Nodes',
      value: props.data
        ? `${props.nodes.length} sichtbar / ${props.data.nodes.length} geladen`
        : null,
    },
    {
      label: 'Edges',
      value: props.data
        ? `${props.edges.length} sichtbar / ${props.data.edges.length} geladen`
        : null,
    },
    {
      label: 'Entity Filter',
      value: entity.success ? nodePresentation[entity.data].label : 'Alle',
    },
    { label: 'Relation Filter', value: relation.success ? relationLabels[relation.data] : 'Alle' },
    { label: 'Geo Scope (Root-Suche)', value: props.geoScope, mono: true },
    {
      label: 'Begrenzung',
      value: props.data?.truncated
        ? `${props.data.max_nodes} Nodes / ${props.data.max_edges} Edges`
        : null,
      tone: 'warning',
    },
  ]
})
defineExpose({ focusRoot: () => graph.value?.focusRoot() })
function selectNode(id: string) {
  detailsOpen.value = true
  emit('select', id)
}
watch(isFullscreen, async (active) => {
  if (active && window.matchMedia('(max-width: 1023px)').matches) detailsOpen.value = false
  await nextTick()
  graph.value?.fitAfterResize()
})
</script>
<template>
  <div ref="fullscreenTarget" class="graph-workspace operations-workspace" :aria-busy="loading">
    <header
      v-if="data || isFullscreen"
      class="workspace-toolbar flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 p-3"
    >
      <div class="min-w-0">
        <p v-if="!isFullscreen && rootNode" class="text-sm font-semibold break-words">
          {{ rootNode.label }}
        </p>
        <h3 v-if="isFullscreen" class="text-sm font-semibold">Beziehungsgraph</h3>
        <p v-if="isFullscreen && rootNode" class="max-w-lg break-words text-xs text-slate-500">
          {{ nodePresentation[rootNode.type].label }} · {{ rootNode.label }}
        </p>
        <p v-if="data" class="text-xs text-slate-600">
          {{ nodes.length }} Knoten · {{ edges.length }} Beziehungen · Tiefe {{ depth }}
        </p>
      </div>
      <div class="flex flex-wrap gap-2" role="group" aria-label="Graph-Steuerung">
        <button
          type="button"
          class="button button-compact"
          :disabled="!data || loading"
          @click="emit('retry')"
        >
          Aktualisieren
        </button>
        <button
          type="button"
          class="button button-compact"
          :disabled="!data || loading"
          @click="graph?.fit()"
        >
          <AppIcon name="fit" :size="16" />Ansicht einpassen
        </button>
        <button
          type="button"
          class="button button-compact"
          :disabled="!data || loading"
          @click="graph?.reset()"
        >
          <AppIcon name="refresh" :size="16" />Ansicht zurücksetzen
        </button>
        <button
          v-if="isFullscreen"
          type="button"
          class="button button-compact"
          :aria-expanded="detailsOpen && !!selectedNode"
          :disabled="!selectedNode"
          @click="detailsOpen = !detailsOpen"
        >
          <AppIcon name="panel" :size="16" />{{
            detailsOpen ? 'Details ausblenden' : 'Details anzeigen'
          }}
        </button>
        <button
          v-if="isSupported"
          type="button"
          class="button button-compact"
          :aria-label="isFullscreen ? 'Vollbild beenden' : 'Graph im Vollbild anzeigen'"
          :aria-pressed="isFullscreen"
          @click="toggleFullscreen"
        >
          <AppIcon :name="isFullscreen ? 'minimize' : 'maximize'" :size="16" />{{
            isFullscreen ? 'Vollbild beenden' : 'Vollbild'
          }}
        </button>
      </div>
    </header>
    <p v-if="fullscreenError" role="status" class="px-3 text-sm text-amber-900">
      {{ fullscreenError }}
    </p>
    <div v-if="loading || error" class="shrink-0 p-3">
      <RequestState :loading="loading" :error="error" :has-data="!!data" @retry="emit('retry')" />
    </div>
    <InlineAlert v-if="data?.truncated" tone="warning" role="status" class="shrink-0">
      Darstellung begrenzt: maximal {{ data.max_nodes }} Knoten und
      {{ data.max_edges }} Beziehungen. Wähle einen anderen Ausgangspunkt oder reduziere die Tiefe.
    </InlineAlert>
    <div
      v-if="data"
      class="workspace-body operations-workspace-main relative flex min-w-0 flex-col overflow-hidden xl:flex-row"
    >
      <EntityGraph
        ref="graph"
        :nodes="nodes"
        :edges="edges"
        :root="root"
        :selected="selected"
        :depth="depth"
        :show-labels="showLabels"
        :fullscreen="isFullscreen"
        workspace-controls
        @select="selectNode"
      />
      <GraphNodeDetails
        v-if="selectedNode && (!isFullscreen || detailsOpen)"
        :node="selectedNode"
        :nodes="nodes"
        :edges="edges"
        :root="root"
        :fullscreen="isFullscreen"
        @close="isFullscreen ? (detailsOpen = false) : emit('select', '')"
        @select="selectNode"
        @root="emit('root', $event)"
      />
    </div>
    <div
      v-else-if="!loading && !error"
      class="m-3 rounded-lg border border-dashed border-slate-300 p-4 text-center"
    >
      <h3 class="text-sm font-semibold">Datensatz auswählen</h3>
      <p class="mt-1 text-sm text-slate-600">
        Suche oben nach einem Datensatz, um dessen Beziehungen zu laden.
      </p>
    </div>
    <footer class="operations-workspace-footer">
      <ul
        aria-label="Graphlegende"
        class="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl bg-white px-3 py-2 text-xs text-slate-500"
      >
        <li v-for="item in nodePresentation" :key="item.label" class="flex items-center gap-1.5">
          <span
            class="grid h-5 w-5 place-items-center rounded-full"
            :style="{
              background: item.fill,
              color: item.color,
              border: `1px solid ${item.border}`,
            }"
            ><AppIcon :name="item.icon" :size="12" /></span
          >{{ item.label }}
        </li>
        <li class="flex items-center gap-1.5">
          <span class="w-6 border-t border-slate-400" />Beziehung
        </li>
        <li class="flex items-center gap-1.5">
          <span class="w-6 border-t border-violet-500" />Ausgewählt
        </li>
      </ul>
      <TechnicalInfoBar :items="technicalItems" :show-title="false" />
    </footer>
  </div>
</template>
<style scoped>
.graph-workspace:fullscreen {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  overflow: hidden;
  padding: env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom)
    env(safe-area-inset-left);
}
.graph-workspace:fullscreen > * {
  margin-block: 0;
}
.graph-workspace:fullscreen .workspace-toolbar {
  flex-shrink: 0;
  border-radius: 0;
}
.graph-workspace:fullscreen .workspace-body {
  flex: 1;
  min-height: 0;
  flex-direction: row;
  border: 0;
  border-radius: 0;
}
.graph-workspace:fullscreen footer {
  flex-shrink: 0;
  border-top: 1px solid #e2e8f0;
}
.graph-workspace:fullscreen footer ul {
  gap: 0.25rem 0.75rem;
}

.graph-workspace > footer {
  border-radius: 0 0 0.75rem 0.75rem;
  overflow: hidden;
}
@media (min-width: 1280px) {
  .graph-workspace :deep(.operations-techbar dl > div:first-child) {
    flex-basis: 14rem;
  }
}
.graph-workspace:fullscreen > footer {
  max-height: 22dvh;
  overflow: auto;
}
.graph-workspace:fullscreen :deep(.operations-techbar dl) {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
}
.graph-workspace:fullscreen :deep(.operations-techbar dl > div) {
  flex: 0 1 auto;
}
</style>
