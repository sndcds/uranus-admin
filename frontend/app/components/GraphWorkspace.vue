<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { GraphNode, GraphEdge, GraphResponse } from '#shared/contracts'
import type { ApiFailure } from '#shared/errors'
import { useFullscreen } from '~/composables/useFullscreen'
import { nodePresentation } from '~/utils/graph'
import AppIcon from './AppIcon.vue'
import EntityGraph from './EntityGraph.vue'
import GraphNodeDetails from './GraphNodeDetails.vue'
import RequestState from './RequestState.vue'
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
  <div ref="fullscreenTarget" class="graph-workspace space-y-3 bg-white" :aria-busy="loading">
    <header
      v-if="data || isFullscreen"
      class="workspace-toolbar flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3"
    >
      <div class="min-w-0">
        <h3 v-if="isFullscreen" class="text-sm font-semibold">Entity-Relationship Graph</h3>
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
          class="button !px-2.5 !py-2 !text-xs"
          :disabled="!data || loading"
          @click="graph?.fit()"
        >
          <AppIcon name="fit" :size="16" />Ansicht einpassen
        </button>
        <button
          type="button"
          class="button !px-2.5 !py-2 !text-xs"
          :disabled="!data || loading"
          @click="graph?.reset()"
        >
          <AppIcon name="refresh" :size="16" />Ansicht zurücksetzen
        </button>
        <button
          v-if="isFullscreen"
          type="button"
          class="button !px-2.5 !py-2 !text-xs"
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
          class="button !px-2.5 !py-2 !text-xs"
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
      <RequestState :loading="loading" :error="error" @retry="emit('retry')" />
    </div>
    <p
      v-if="data?.truncated"
      role="status"
      class="shrink-0 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
    >
      Darstellung begrenzt: maximal {{ data.max_nodes }} Knoten und
      {{ data.max_edges }} Beziehungen. Wähle einen anderen Ausgangspunkt oder reduziere die Tiefe.
    </p>
    <div
      v-if="data"
      class="workspace-body relative flex min-w-0 flex-col overflow-hidden rounded-xl border border-slate-200 xl:flex-row"
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
      class="grid min-h-[540px] place-items-center rounded-xl border border-slate-200 bg-white p-8 text-center"
    >
      <div class="max-w-md">
        <span
          class="mx-auto mb-5 grid h-20 w-20 place-items-center rounded-3xl bg-fuchsia-50 text-fuchsia-600"
          ><AppIcon name="graph" :size="36"
        /></span>
        <h3 class="text-lg font-semibold">Zusammenhänge entdecken</h3>
        <p class="mt-2 text-sm leading-6 text-slate-500">
          Suche nach einem Namen oder einer UUID und wähle einen Datensatz als Ausgangspunkt. Von
          dort erkundest du seine Orte, Veranstaltungen und weiteren Beziehungen.
        </p>
        <p class="mt-4 text-xs text-slate-400">Mindestens 2 Zeichen · Bis zu 3 Ebenen</p>
      </div>
    </div>
    <footer class="flex flex-wrap items-center justify-between gap-3">
      <ul
        aria-label="Graphlegende"
        class="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl bg-white px-3 py-2 text-[10px] text-slate-500"
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
</style>
