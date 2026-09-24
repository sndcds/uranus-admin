<script setup lang="ts">
import VenueScopeBadge from './VenueScopeBadge.vue'
import { computed, ref, watch } from 'vue'
import type { GraphNode, GraphEdge } from '#shared/contracts'
import { nodePresentation } from '~/utils/graph'
import { activityStatus } from '~/utils/activity'
import AppIcon from './AppIcon.vue'
import CopyValueButton from './CopyValueButton.vue'
const props = defineProps<{
  node: GraphNode
  nodes: GraphNode[]
  edges: GraphEdge[]
  root: string
  fullscreen?: boolean
}>()
defineEmits<{ close: []; select: [id: string]; root: [node: GraphNode] }>()
const tab = ref('all')
const relations = computed(() =>
  props.edges
    .filter((e) => e.source === props.node.id || e.target === props.node.id)
    .map((edge) => ({
      edge,
      node: props.nodes.find(
        (n) => n.id === (edge.source === props.node.id ? edge.target : edge.source),
      )!,
    }))
    .filter((r) => r.node),
)
const events = computed(() =>
  relations.value.filter((r) => ['event', 'event_date'].includes(r.node.type)),
)
const places = computed(() =>
  relations.value.filter((r) => ['venue', 'space'].includes(r.node.type)),
)
const visible = computed(() =>
  tab.value === 'events' ? events.value : tab.value === 'places' ? places.value : relations.value,
)
watch(
  () => props.node.id,
  () => {
    tab.value = 'all'
  },
)
</script>
<template>
  <aside
    :class="{ 'graph-details-fullscreen': fullscreen }"
    class="graph-details operations-workspace-sidebar flex min-w-0 flex-col border-t border-slate-200 xl:border-l xl:border-t-0 [overflow-wrap:anywhere]"
    aria-label="Knotendetails"
  >
    <div class="p-3">
      <p class="operations-meta mb-1">Auswahl</p>
      <div class="flex items-start justify-between gap-3">
        <h3 class="text-sm font-bold leading-5">{{ node.label }}</h3>
        <button
          class="grid min-h-11 min-w-11 place-items-center rounded text-slate-600 hover:bg-slate-100"
          aria-label="Details schließen"
          @click="$emit('close')"
        >
          <AppIcon name="close" :size="16" />
        </button>
      </div>
      <div class="my-2 flex items-center gap-2">
        <div
          class="grid h-9 w-9 place-items-center rounded-xl"
          :style="{
            color: nodePresentation[node.type].color,
            background: nodePresentation[node.type].fill,
          }"
        >
          <AppIcon :name="nodePresentation[node.type].icon" :size="25" />
        </div>
        <div class="min-w-0">
          <p class="text-xs font-medium">{{ nodePresentation[node.type].label }}</p>
          <VenueScopeBadge
            v-if="node.type === 'venue' && node.venue_scope"
            :scope="node.venue_scope"
          />
          <p
            v-if="node.status"
            class="mt-1 inline-block rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600"
          >
            {{ activityStatus(node.status) }}
          </p>
        </div>
      </div>
      <dl class="grid grid-cols-[45px_minmax(0,1fr)] gap-x-3 gap-y-3 text-xs leading-5">
        <dt class="text-slate-500">UUID</dt>
        <dd class="flex min-w-0 flex-wrap items-center gap-x-2">
          <span class="min-w-0 break-all font-mono text-xs">{{ node.key }}</span>
          <CopyValueButton
            :value="node.key"
            label="UUID"
            success-message="UUID kopiert"
            :reset-key="node.id"
          />
        </dd>
        <template v-if="node.subtitle"
          ><dt class="text-slate-500">Details</dt>
          <dd>{{ node.subtitle }}</dd></template
        >
      </dl>
      <div class="mt-5 flex flex-wrap gap-2">
        <NuxtLink v-if="node.admin_url" :to="node.admin_url" class="button"
          ><AppIcon name="external" :size="13" />Öffnen</NuxtLink
        ><a
          v-if="node.public_url"
          :href="node.public_url"
          target="_blank"
          rel="noopener noreferrer"
          referrerpolicy="no-referrer"
          :aria-label="`${node.label} auf kulturbytes.de öffnen (neuer Tab)`"
          class="button"
          ><AppIcon name="external" :size="13" />Auf kulturbytes.de öffnen</a
        >
        <button
          class="button button-compact"
          :disabled="node.id === root"
          title="Als Ausgangspunkt verwenden"
          @click="$emit('root', node)"
        >
          <AppIcon name="graph" :size="14" />Beziehungen
        </button>
        <RecordMarkLink :entity-type="node.type" :entity-key="node.key" variant="compact" />
      </div>
    </div>
    <div
      class="flex flex-wrap border-b border-slate-100 px-3 text-xs"
      role="group"
      aria-label="Beziehungen filtern"
    >
      <button
        v-for="item in [
          { key: 'all', label: 'Beziehungen', count: relations.length },
          { key: 'events', label: 'Veranstaltungen', count: events.length },
          { key: 'places', label: 'Orte & Räume', count: places.length },
        ]"
        :key="item.key"
        class="min-h-11 whitespace-nowrap border-b-2 px-1.5 py-3"
        :class="
          tab === item.key
            ? 'border-fuchsia-600 font-semibold text-fuchsia-700'
            : 'border-transparent text-slate-500'
        "
        :aria-pressed="tab === item.key"
        @click="tab = item.key"
      >
        {{ item.label }} ({{ item.count }})
      </button>
    </div>
    <p class="px-4 pt-3 text-xs text-slate-400">Direkte Beziehungen im geladenen Graph</p>
    <ul class="min-h-24 flex-1 overflow-auto px-4 py-1" aria-label="Direkte Beziehungen">
      <li
        v-for="item in visible"
        :key="item.edge.id"
        class="border-b border-slate-100 last:border-0"
      >
        <button
          class="flex w-full items-center gap-2 rounded py-3 text-left hover:bg-slate-50"
          @click="$emit('select', item.node.id)"
        >
          <span
            class="grid h-8 w-8 shrink-0 place-items-center rounded-lg"
            :style="{
              background: nodePresentation[item.node.type].fill,
              color: nodePresentation[item.node.type].color,
            }"
            ><AppIcon :name="nodePresentation[item.node.type].icon" :size="17" /></span
          ><span class="min-w-0 flex-1"
            ><span class="block text-xs font-semibold leading-4">{{ item.node.label }}</span
            ><span class="text-xs text-slate-500">{{
              nodePresentation[item.node.type].label
            }}</span>
            <VenueScopeBadge
              v-if="item.node.type === 'venue' && item.node.venue_scope"
              :scope="item.node.venue_scope"
            /> </span
          ><span
            class="max-w-24 rounded bg-slate-100 px-1.5 py-1 text-xs text-slate-500"
            :title="`${item.edge.source === node.id ? node.label : item.node.label} → ${item.edge.label} → ${item.edge.target === node.id ? node.label : item.node.label}`"
            >{{ item.edge.source === node.id ? '→' : '←' }} {{ item.edge.label }}</span
          >
        </button>
      </li>
    </ul>
    <p v-if="!visible.length" class="p-4 text-xs text-slate-500">
      Keine Beziehungen in dieser Auswahl.
    </p>
  </aside>
</template>
<style scoped>
.graph-details {
  width: 100%;
}
@media (min-width: 1280px) {
  .graph-details {
    width: 300px;
    flex-shrink: 0;
    max-height: min(72vh, 800px);
    min-height: 520px;
    overflow: auto;
  }
}
.graph-details-fullscreen {
  position: absolute;
  z-index: 2;
  top: 0;
  right: 0;
  bottom: 0;
  width: min(320px, 88%);
  min-height: 0;
  max-height: 100%;
  overflow: auto;
  border-top: 0;
  border-left: 1px solid #e2e8f0;
  box-shadow: -4px 0 16px rgb(15 23 42 / 0.08);
}
@media (min-width: 1024px) {
  .graph-details-fullscreen {
    position: static;
    width: 360px;
    flex-shrink: 0;
    box-shadow: none;
  }
}
</style>
