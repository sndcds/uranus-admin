<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { GraphNode, GraphEdge } from '#shared/contracts'
import { nodePresentation } from '~/utils/graph'
import { activityStatus } from '~/utils/activity'
import AppIcon from './AppIcon.vue'
const props = defineProps<{
  node: GraphNode
  nodes: GraphNode[]
  edges: GraphEdge[]
  root: string
}>()
defineEmits<{ close: []; select: [id: string]; root: [node: GraphNode] }>()
const tab = ref('all')
const copied = ref('')
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
    copied.value = ''
  },
)
async function copy() {
  try {
    await navigator.clipboard.writeText(props.node.key)
    copied.value = 'UUID kopiert'
  } catch {
    copied.value = 'Kopieren nicht verfügbar'
  }
}
</script>
<template>
  <aside
    class="graph-details flex min-w-0 flex-col border-t border-slate-200 bg-white xl:border-l xl:border-t-0"
    aria-label="Knotendetails"
  >
    <div class="p-4">
      <div class="flex items-start justify-between gap-3">
        <h3 class="text-sm font-bold leading-5">{{ node.label }}</h3>
        <button
          class="rounded p-1 text-slate-400 hover:bg-slate-50"
          aria-label="Details schließen"
          @click="$emit('close')"
        >
          <AppIcon name="close" :size="16" />
        </button>
      </div>
      <div class="my-4 flex items-center gap-3">
        <div
          class="grid h-12 w-12 place-items-center rounded-xl"
          :style="{
            color: nodePresentation[node.type].color,
            background: nodePresentation[node.type].fill,
          }"
        >
          <AppIcon :name="nodePresentation[node.type].icon" :size="25" />
        </div>
        <div>
          <p class="text-xs font-medium">{{ nodePresentation[node.type].label }}</p>
          <p
            v-if="node.status"
            class="mt-1 inline-block rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600"
          >
            {{ activityStatus(node.status) }}
          </p>
        </div>
      </div>
      <dl class="grid grid-cols-[45px_minmax(0,1fr)] gap-x-3 gap-y-3 text-xs leading-5">
        <dt class="text-slate-500">Name</dt>
        <dd>{{ node.label }}</dd>
        <dt class="text-slate-500">UUID</dt>
        <dd class="flex min-w-0 items-start gap-1">
          <span class="break-all text-[10px]">{{ node.key }}</span
          ><button
            class="shrink-0 rounded p-1 text-slate-500"
            aria-label="UUID kopieren"
            @click="copy"
          >
            <AppIcon name="copy" :size="12" />
          </button>
        </dd>
        <template v-if="node.subtitle"
          ><dt class="text-slate-500">Details</dt>
          <dd>{{ node.subtitle }}</dd></template
        >
      </dl>
      <p v-if="copied" role="status" class="mt-2 text-xs text-slate-500">{{ copied }}</p>
      <div class="mt-5 flex flex-wrap gap-2">
        <NuxtLink
          v-if="node.admin_url"
          :to="node.admin_url"
          class="flex items-center gap-2 rounded-lg bg-fuchsia-50 px-3 py-2 text-[11px] font-medium text-fuchsia-700"
          ><AppIcon name="external" :size="13" />Im Admin ansehen</NuxtLink
        ><a
          v-if="node.public_url"
          :href="node.public_url"
          target="_blank"
          rel="noopener noreferrer"
          referrerpolicy="no-referrer"
          class="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-[11px]"
          ><AppIcon name="external" :size="13" />Zur Live-Seite</a
        >
      </div>
    </div>
    <div
      class="flex border-b border-slate-100 px-3 text-[10px]"
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
        class="whitespace-nowrap border-b-2 px-1.5 py-3"
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
    <p class="px-4 pt-3 text-[10px] text-slate-400">Direkte Beziehungen im geladenen Graph</p>
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
            ><span class="block text-[11px] font-semibold leading-4">{{ item.node.label }}</span
            ><span class="text-[10px] text-slate-500">{{
              nodePresentation[item.node.type].label
            }}</span></span
          ><span
            class="max-w-24 rounded bg-slate-100 px-1.5 py-1 text-[9px] text-slate-500"
            :title="`${item.edge.source === node.id ? node.label : item.node.label} → ${item.edge.label} → ${item.edge.target === node.id ? node.label : item.node.label}`"
            >{{ item.edge.source === node.id ? '→' : '←' }} {{ item.edge.label }}</span
          >
        </button>
      </li>
    </ul>
    <p v-if="!visible.length" class="p-4 text-xs text-slate-500">
      Keine Beziehungen in dieser Auswahl.
    </p>
    <div class="space-y-3 border-t border-slate-100 p-4">
      <p class="text-xs font-medium">Weiter erkunden</p>
      <button
        class="button w-full !rounded-lg !text-xs"
        :disabled="node.id === root"
        @click="$emit('root', node)"
      >
        <AppIcon name="graph" :size="14" />Als Ausgangspunkt verwenden
      </button>
    </div>
  </aside>
</template>
<style scoped>
.graph-details {
  width: 100%;
}
@media (min-width: 1280px) {
  .graph-details {
    width: 320px;
    flex-shrink: 0;
    max-height: min(72vh, 800px);
    min-height: 520px;
  }
}
</style>
