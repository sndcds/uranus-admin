<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  shallowRef,
  triggerRef,
  useId,
  watch,
} from 'vue'
import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from 'd3-force'
import type { Simulation } from 'd3-force'
import { select } from 'd3-selection'
import { zoom, zoomIdentity } from 'd3-zoom'
import type { ZoomBehavior, D3ZoomEvent } from 'd3-zoom'
import { drag } from 'd3-drag'
import type { D3DragEvent } from 'd3-drag'
import type { GraphNode, GraphEdge } from '#shared/contracts'
import { graphDataToSimulation, labelLines, nodePresentation } from '~/utils/graph'
import type { GraphSimulationNode, GraphSimulationLink } from '~/utils/graph'
import AppIcon from './AppIcon.vue'
const props = defineProps<{
  nodes: GraphNode[]
  edges: GraphEdge[]
  root: string
  selected: string
  depth: number
  showLabels: boolean
  fullscreen?: boolean
  workspaceControls?: boolean
}>()
const emit = defineEmits<{ select: [id: string] }>()
const svg = ref<SVGSVGElement>()
const points = shallowRef<GraphSimulationNode[]>([])
const links = shallowRef<GraphSimulationLink[]>([])
const transform = ref('translate(450,350)')
const dimensions = ref({ width: 900, height: 700 })
let observer: ResizeObserver | undefined
let fitFrame: number | undefined
function fitAfterResize() {
  if (fitFrame !== undefined) cancelAnimationFrame(fitFrame)
  // Two frames allow the fullscreen layout and ResizeObserver to settle first.
  fitFrame = requestAnimationFrame(() => {
    fitFrame = requestAnimationFrame(() => {
      fitFrame = undefined
      fit()
    })
  })
}
const markerId = `graph-arrow-${useId().replace(/:/g, '')}`
let simulation: Simulation<GraphSimulationNode, GraphSimulationLink> | undefined
let zoomBehavior: ZoomBehavior<SVGSVGElement, unknown> | undefined
const neighbors = computed(
  () =>
    new Set(
      props.edges
        .filter((e) => e.source === props.selected || e.target === props.selected)
        .flatMap((e) => [e.source, e.target]),
    ),
)
const connected = (id: string) =>
  !props.selected || id === props.selected || neighbors.value.has(id)
function endpoint(value: GraphSimulationLink['source']) {
  return value as GraphSimulationNode
}
function line(edge: GraphSimulationLink) {
  const a = endpoint(edge.source),
    b = endpoint(edge.target)
  const dx = (b.x ?? 0) - (a.x ?? 0),
    dy = (b.y ?? 0) - (a.y ?? 0)
  const length = Math.hypot(dx, dy) || 1
  const r1 = a.id === props.root ? 35 : 28,
    r2 = b.id === props.root ? 39 : 32
  return {
    x1: (a.x ?? 0) + (dx / length) * r1,
    y1: (a.y ?? 0) + (dy / length) * r1,
    x2: (b.x ?? 0) - (dx / length) * r2,
    y2: (b.y ?? 0) - (dy / length) * r2,
  }
}
function fit() {
  if (!svg.value || !zoomBehavior || !points.value.length) return
  const xs = points.value.map((n) => n.x ?? 0),
    ys = points.value.map((n) => n.y ?? 0)
  const x0 = Math.min(...xs) - 85,
    x1 = Math.max(...xs) + 85
  const y0 = Math.min(...ys) - 95,
    y1 = Math.max(...ys) + 95
  const k = Math.min(
    1.3,
    (dimensions.value.width - 30) / (x1 - x0),
    (dimensions.value.height - 70) / (y1 - y0),
  )
  select(svg.value).call(
    zoomBehavior.transform,
    zoomIdentity
      .translate(
        dimensions.value.width / 2 - ((x0 + x1) / 2) * k,
        dimensions.value.height / 2 + 15 - ((y0 + y1) / 2) * k,
      )
      .scale(k),
  )
}
function scale(factor: number) {
  if (svg.value && zoomBehavior) select(svg.value).call(zoomBehavior.scaleBy, factor)
}
async function start() {
  simulation?.stop()
  const data = graphDataToSimulation(props.nodes, props.edges, props.root)
  points.value = data.nodes
  links.value = data.links
  simulation = forceSimulation(data.nodes)
    .force(
      'link',
      forceLink<GraphSimulationNode, GraphSimulationLink>(data.links)
        .id((n) => n.id)
        .distance(155)
        .strength(0.45),
    )
    .force('charge', forceManyBody().strength(-650))
    .force('center', forceCenter(0, 0))
    .force(
      'collision',
      forceCollide<GraphSimulationNode>((n) => (n.id === props.root ? 85 : 65)),
    )
    .stop()
  // Stable first paint; no unbounded animation, random screenshots or motion on mount.
  simulation.tick(180)
  simulation.on('tick', () => triggerRef(points))
  triggerRef(points)
  await nextTick()
  if (!svg.value) return
  select(svg.value)
    .selectAll<SVGGElement, GraphSimulationNode>('.graph-node')
    .data(data.nodes, function (n) {
      return n?.id ?? this.getAttribute('data-id') ?? ''
    })
    .call(
      drag<SVGGElement, GraphSimulationNode>()
        .on(
          'start',
          (event: D3DragEvent<SVGGElement, GraphSimulationNode, GraphSimulationNode>, n) => {
            event.sourceEvent.stopPropagation()
            if (!event.active) simulation?.alphaTarget(0.12).restart()
            n.fx = n.x
            n.fy = n.y
          },
        )
        .on(
          'drag',
          (event: D3DragEvent<SVGGElement, GraphSimulationNode, GraphSimulationNode>, n) => {
            n.fx = event.x
            n.fy = event.y
          },
        )
        .on('end', () => {
          simulation?.alphaTarget(0)
        }),
    )
  fit()
}
onMounted(() => {
  if (!svg.value) return
  zoomBehavior = zoom<SVGSVGElement, unknown>()
    .extent((): [[number, number], [number, number]] => [
      [0, 0],
      [dimensions.value.width, dimensions.value.height],
    ])
    .scaleExtent([0.15, 4])
    .on('zoom', (event: D3ZoomEvent<SVGSVGElement, unknown>) => {
      transform.value = event.transform.toString()
    })
  select(svg.value).call(zoomBehavior).on('dblclick.zoom', null)
  let measured = false
  observer = new ResizeObserver(([entry]) => {
    if (!entry?.contentRect.width || !entry.contentRect.height) return
    dimensions.value = { width: entry.contentRect.width, height: entry.contentRect.height }
    if (!measured) {
      measured = true
      fit()
    }
    // Preserve manual zoom/pan on ordinary resizes. Fullscreen explicitly fits once.
  })
  observer.observe(svg.value)
  void start()
})
watch(
  () => [props.nodes, props.edges, props.root],
  () => {
    void start()
  },
)
onBeforeUnmount(() => {
  if (fitFrame !== undefined) cancelAnimationFrame(fitFrame)
  observer?.disconnect()
  simulation?.stop()
  if (svg.value) {
    select(svg.value).on('.zoom', null)
    select(svg.value).selectAll('.graph-node').on('.drag', null)
  }
})
function focusRoot() {
  const node = [...(svg.value?.querySelectorAll<SVGGElement>('.graph-node') ?? [])].find(
    (element) => element.dataset.id === props.root,
  )
  node?.focus({ preventScroll: true })
}
defineExpose({ fit, fitAfterResize, reset: start, focusRoot })
</script>
<template>
  <div
    :class="{ 'graph-canvas-fullscreen': fullscreen }"
    class="graph-canvas relative min-w-0 flex-1 overflow-hidden bg-white"
  >
    <div
      v-if="!workspaceControls"
      class="absolute left-4 top-4 z-[1] flex items-center gap-5 rounded-lg border border-slate-200 bg-white/95 px-3 py-2 text-xs shadow-sm"
    >
      <div>
        <strong class="font-semibold"
          >{{ nodes.length }} Knoten · {{ edges.length }} Beziehungen</strong
        >
        <p class="mt-0.5 text-slate-500">
          Geladen · {{ depth }} {{ depth === 1 ? 'Ebene' : 'Ebenen' }}
        </p>
      </div>
      <button
        aria-label="Ansicht einpassen"
        class="rounded p-1 text-slate-500 hover:bg-slate-100"
        @click="fit"
      >
        <AppIcon name="fit" :size="15" />
      </button>
    </div>
    <svg
      ref="svg"
      :viewBox="`0 0 ${dimensions.width} ${dimensions.height}`"
      class="h-full min-h-[520px] w-full touch-none"
      role="group"
      aria-label="Interaktiver Beziehungsgraph. Knoten mit Tab auswählen und mit Enter öffnen. Ziehen verschiebt Knoten, Mausrad zoomt."
    >
      <defs>
        <marker
          :id="markerId"
          viewBox="0 -4 8 8"
          refX="7"
          refY="0"
          markerWidth="7"
          markerHeight="7"
          orient="auto"
        >
          <path d="M0,-3 L7,0 L0,3" fill="#94a3b8" />
        </marker>
      </defs>
      <g :transform="transform">
        <g
          v-for="edge in links"
          :key="edge.id"
          :opacity="
            !selected ||
            edge.source === selected ||
            endpoint(edge.source).id === selected ||
            endpoint(edge.target).id === selected
              ? 1
              : 0.6
          "
        >
          <line
            v-bind="line(edge)"
            stroke="#94a3b8"
            stroke-width="1"
            :marker-end="edge.direction === 'directed' ? `url(#${markerId})` : undefined"
            :stroke-dasharray="
              edge.type.includes('request') || edge.type.includes('invited') ? '4 4' : undefined
            "
          />
          <g
            v-if="
              showLabels &&
              (links.length < 35 ||
                endpoint(edge.source).id === selected ||
                endpoint(edge.target).id === selected)
            "
            :transform="`translate(${((endpoint(edge.source).x ?? 0) + (endpoint(edge.target).x ?? 0)) / 2},${((endpoint(edge.source).y ?? 0) + (endpoint(edge.target).y ?? 0)) / 2})`"
          >
            <rect
              :x="-(edge.label.length * 2.8 + 7)"
              y="-10"
              :width="edge.label.length * 5.6 + 14"
              height="19"
              rx="5"
              fill="#f1f5f9"
            />
            <text text-anchor="middle" y="3" font-size="10" fill="#64748b">{{ edge.label }}</text>
          </g>
        </g>
        <g
          v-for="node in points"
          :key="node.id"
          class="graph-node cursor-pointer outline-none"
          :data-id="node.id"
          :transform="`translate(${node.x ?? 0},${node.y ?? 0})`"
          :opacity="connected(node.id) ? 1 : 0.65"
          role="button"
          tabindex="0"
          :aria-label="`${node.label}, ${nodePresentation[node.type].label}`"
          :aria-pressed="selected === node.id"
          @click="emit('select', node.id)"
          @keydown.enter.prevent="emit('select', node.id)"
          @keydown.space.prevent="emit('select', node.id)"
        >
          <title>{{ node.label }} · {{ nodePresentation[node.type].label }}</title>
          <circle
            class="node-focus"
            :r="node.id === root ? 40 : 33"
            fill="none"
            stroke="#a855f7"
            stroke-width="2"
            opacity="0"
          />
          <circle
            :r="node.id === root ? 34 : 27"
            :fill="nodePresentation[node.type].fill"
            :stroke="selected === node.id ? '#a855f7' : nodePresentation[node.type].border"
            :stroke-width="selected === node.id ? 1.8 : 1"
          />
          <AppIcon
            :name="nodePresentation[node.type].icon"
            :size="node.id === root ? 28 : 23"
            :x="node.id === root ? -14 : -11.5"
            :y="node.id === root ? -14 : -11.5"
            :color="nodePresentation[node.type].color"
          />
          <text
            text-anchor="middle"
            :y="node.id === root ? 48 : 41"
            font-size="12"
            :font-weight="node.id === root || selected === node.id ? 650 : 500"
            :fill="selected === node.id ? '#0f172a' : '#475569'"
          >
            <tspan
              v-for="(label, i) in labelLines(node.label)"
              :key="i"
              x="0"
              :dy="i === 0 ? 0 : 14"
            >
              {{ label }}
            </tspan>
          </text>
        </g>
      </g>
    </svg>
    <div
      class="absolute bottom-4 left-4 flex flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm"
    >
      <button
        class="min-h-11 min-w-11 p-2 hover:bg-slate-50"
        aria-label="Vergrößern"
        @click="scale(1.3)"
      >
        <AppIcon name="plus" :size="16" />
      </button>
      <button
        class="min-h-11 min-w-11 border-y border-slate-100 p-2 hover:bg-slate-50"
        aria-label="Verkleinern"
        @click="scale(1 / 1.3)"
      >
        <AppIcon name="minus" :size="16" />
      </button>
      <button
        v-if="!workspaceControls"
        class="min-h-11 min-w-11 p-2 hover:bg-slate-50"
        aria-label="Ansicht zurücksetzen"
        @click="start"
      >
        <AppIcon name="refresh" :size="15" />
      </button>
    </div>
    <p v-if="nodes.length === 1" class="absolute bottom-5 left-16 right-4 text-xs text-slate-500">
      Keine weiteren Beziehungen in dieser Auswahl.
    </p>
  </div>
</template>
<style scoped>
.graph-canvas {
  height: min(72vh, 800px);
  min-height: 520px;
}
.graph-node:focus-visible .node-focus {
  opacity: 1;
}
@media (max-width: 640px) {
  .graph-canvas {
    height: 520px;
  }
}
.graph-canvas-fullscreen {
  height: 100%;
  min-height: 0;
}
.graph-canvas-fullscreen > svg {
  min-height: 0;
}
</style>
