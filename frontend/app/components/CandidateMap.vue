<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Map as LeafletMap, Marker, TileLayer } from 'leaflet'
import type { GeocodeCandidate } from '#shared/contracts'
import { mapAttributionUrl, mapTileUrl } from '~/utils/map-tiles'
import 'leaflet/dist/leaflet.css'

const props = defineProps<{
  candidates: GeocodeCandidate[]
  selectedId: string
  embedded?: boolean
}>()
const emit = defineEmits<{ select: [id: string] }>()
const config = useRuntimeConfig().public
const tileUrl = mapTileUrl(config.mapTileUrl)
const attributionUrl = mapAttributionUrl(config.mapTileAttributionUrl)
const container = ref<HTMLElement>()
const failed = ref(false)
const ready = ref(false)
const unavailable = computed(() => !tileUrl || failed.value)
let leaflet: typeof import('leaflet') | undefined
let map: LeafletMap | undefined
let tiles: TileLayer | undefined
let observer: ResizeObserver | undefined
let disposed = false
let timeout: ReturnType<typeof setTimeout> | undefined
const markers = new Map<string, { marker: Marker; button: HTMLButtonElement }>()

function clearDeadline() {
  clearTimeout(timeout)
}
function fail() {
  if (disposed) return
  failed.value = true
  clearDeadline()
  // Stop loading more tiles after failure. No automatic retry or provider fallback.
  tiles?.remove()
}
function loading() {
  clearDeadline()
  timeout = setTimeout(fail, 12000)
}
function fitAll() {
  if (!map || !leaflet || !props.candidates.length) return
  const positions = props.candidates.map((c): [number, number] => [c.latitude, c.longitude])
  map.fitBounds(leaflet.latLngBounds(positions), { padding: [48, 48], maxZoom: 16, animate: false })
}
function highlight() {
  for (const [id, { marker, button }] of markers) {
    const selected = id === props.selectedId
    button.setAttribute('aria-pressed', String(selected))
    marker.setZIndexOffset(selected ? 1000 : 0)
  }
}
function focusCandidate(id: string, reveal = false) {
  const candidate = props.candidates.find((c) => c.id === id)
  if (!map || !candidate || unavailable.value) return
  map.setView([candidate.latitude, candidate.longitude], 16, { animate: false })
  if (reveal) {
    container.value?.focus({ preventScroll: true })
    container.value?.scrollIntoView({ block: 'nearest' })
  }
}
function renderCandidates() {
  if (!map || !leaflet) return
  for (const { marker } of markers.values()) marker.remove()
  markers.clear()
  for (const candidate of props.candidates) {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'candidate-map-marker'
    button.textContent = String(candidate.rank)
    button.setAttribute(
      'aria-label',
      `Kandidat ${candidate.rank} auf der Karte: ${candidate.display_name}`,
    )
    button.addEventListener('click', () => emit('select', candidate.id))
    const marker = leaflet
      .marker([candidate.latitude, candidate.longitude], {
        icon: leaflet.divIcon({
          html: button,
          className: 'candidate-map-icon',
          iconSize: [44, 44],
          iconAnchor: [22, 22],
        }),
        keyboard: false,
      })
      .addTo(map)
    markers.set(candidate.id, { marker, button })
  }
  highlight()
  fitAll()
}
watch(() => props.candidates, renderCandidates, { deep: true })
watch(
  () => props.selectedId,
  (id) => {
    highlight()
    focusCandidate(id)
  },
)
onMounted(async () => {
  if (!tileUrl || !props.candidates.length) return
  loading()
  try {
    leaflet = await import('leaflet')
    if (disposed || failed.value || !container.value) return
    map = leaflet.map(container.value, {
      attributionControl: false, // Escaped Vue attribution remains visible below the map.
      zoomControl: false,
      scrollWheelZoom: false,
      minZoom: 1,
      maxZoom: 19,
    })
    leaflet.control.zoom({ zoomInTitle: 'Vergrößern', zoomOutTitle: 'Verkleinern' }).addTo(map)
    tiles = leaflet.tileLayer(tileUrl, {
      maxZoom: 19,
      referrerPolicy: 'origin',
      keepBuffer: 0,
    })
    tiles.on('loading', loading)
    tiles.on('load', () => {
      clearDeadline()
      ready.value = true
    })
    tiles.on('tileerror', fail)
    renderCandidates()
    tiles.addTo(map)
    observer = new ResizeObserver(() => map?.invalidateSize({ pan: false }))
    observer.observe(container.value)
  } catch {
    fail()
  }
})
onBeforeUnmount(() => {
  disposed = true
  clearDeadline()
  observer?.disconnect()
  tiles?.off()
  map?.remove()
  markers.clear()
})
defineExpose({ focusCandidate })
</script>

<template>
  <section
    class="candidate-map min-w-0 overflow-hidden"
    :class="embedded ? '' : 'panel'"
    aria-label="Karte der Standortkandidaten"
  >
    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 p-3">
      <span class="text-sm text-slate-600"
        >{{ candidates.length }} {{ candidates.length === 1 ? 'Kandidat' : 'Kandidaten' }} · Norden
        oben</span
      >
      <button v-if="!unavailable && candidates.length" type="button" class="button" @click="fitAll">
        {{ candidates.length === 1 ? 'Zentrieren' : 'Alle Kandidaten zeigen' }}
      </button>
    </div>
    <div v-if="!candidates.length" class="p-4 text-sm text-slate-600">
      Keine Standortkandidaten vorhanden.
    </div>
    <div v-else-if="unavailable" class="p-4">
      <InlineAlert tone="warning"
        >Karte konnte nicht geladen werden. Die Standortkandidaten können weiterhin in der Liste
        geprüft werden.</InlineAlert
      >
    </div>
    <div v-show="candidates.length && !unavailable" class="relative">
      <div
        ref="container"
        class="candidate-map-canvas"
        aria-label="Interaktive Karte; Pfeiltasten zum Verschieben, Plus und Minus zum Zoomen"
      />
      <p
        v-if="!ready"
        role="status"
        class="pointer-events-none absolute bottom-3 left-3 z-[1000] rounded bg-white px-3 py-2 text-sm"
      >
        Karte wird geladen…
      </p>
    </div>
    <div
      class="flex flex-wrap gap-x-2 gap-y-1 border-t border-slate-200 px-3 py-2 text-xs text-slate-600"
    >
      <OsmAttribution />
      <template v-if="config.mapTileAttribution">
        <a
          v-if="attributionUrl"
          :href="attributionUrl"
          target="_blank"
          rel="noopener noreferrer"
          referrerpolicy="no-referrer"
          >{{ config.mapTileAttribution }}</a
        >
        <span v-else>{{ config.mapTileAttribution }}</span>
      </template>
    </div>
  </section>
</template>

<style>
.candidate-map-canvas {
  height: 320px;
  width: 100%;
  z-index: 0;
  background: #e2e8f0;
}
@media (min-width: 640px) {
  .candidate-map-canvas {
    height: 420px;
  }
}
.candidate-map-marker {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: 3px solid #475569;
  background: white;
  color: #1e293b;
  font: bold 16px/1 system-ui;
  cursor: pointer;
  box-shadow: 0 2px 5px #0004;
}
.candidate-map-marker[aria-pressed='true'] {
  background: #a21caf;
  border-color: #701a75;
  color: white;
  box-shadow:
    0 0 0 4px #fff,
    0 2px 8px #0006;
}
.candidate-map-marker:focus-visible {
  outline: 3px solid #a21caf;
  outline-offset: 5px;
}
.candidate-map .leaflet-control-zoom a {
  width: 44px;
  height: 44px;
  line-height: 44px;
}
</style>
