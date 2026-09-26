<script setup lang="ts">
import type { ResearchRecord } from '#shared/contracts'
import { researchKey, researchLabels, researchHref } from '~/utils/research'
const props = defineProps<{ items: ResearchRecord[]; selected: string }>()
const emit = defineEmits<{ select: [id: string] }>()
const panel = ref<HTMLElement | null>(null)
const fullscreen = useFullscreen(panel)
const map = useTemplateRef('map')
function reveal() {
  panel.value?.scrollIntoView({ block: 'center', behavior: 'instant' })
  map.value?.focusPoint(props.selected, true)
}
defineExpose({ reveal })
const points = computed(() =>
  props.items.flatMap((item, index) =>
    item.location
      ? [
          {
            id: researchKey(item),
            rank: index + 1,
            tone:
              item.entity_type === 'venue'
                ? ('teal' as const)
                : item.entity_type === 'organization'
                  ? ('violet' as const)
                  : ('blue' as const),
            display_name: `${researchLabels[item.entity_type]}: ${item.name}`,
            ...item.location,
          },
        ]
      : [],
  ),
)
function popupContent(id: string) {
  const content = document.createElement('div')
  const item = props.items.find((item) => researchKey(item) === id)
  if (!item) return content
  content.className = 'research-popup-content'
  if (item.image_url) {
    const image = document.createElement('img')
    image.src = item.image_url
    image.alt = ''
    image.referrerPolicy = 'no-referrer'
    content.append(image)
  }
  const body = document.createElement('div')
  const title = document.createElement('strong')
  title.textContent = item.name
  const type = document.createElement('p')
  type.textContent = researchLabels[item.entity_type]
  body.append(title, type)
  if (item.entity_type === 'event') {
    for (const value of [
      item.venue_name,
      item.all_day
        ? 'Ganztägig'
        : item.start_time
          ? item.start_time.slice(0, 5) + (item.end_time ? ' – ' + item.end_time.slice(0, 5) : '')
          : null,
    ]) {
      if (!value) continue
      const fact = document.createElement('p')
      fact.textContent = value
      body.append(fact)
    }
  }
  if (item.event_count !== null) {
    const count = document.createElement('p')
    count.textContent = `${item.event_count} Veranstaltungen im Filter`
    body.append(count)
  }
  const link = document.createElement('a')
  link.href = researchHref(item.entity_type, item.entity_key)
  link.textContent = 'Details anzeigen →'
  body.append(link)
  content.append(body)
  return content
}
</script>
<template>
  <section
    ref="panel"
    class="research-map relative min-w-0 overflow-hidden rounded-lg border border-slate-200 bg-white"
    aria-label="Recherche-Karte"
  >
    <button
      v-if="fullscreen.isSupported.value"
      class="button absolute right-2 top-2 z-10"
      @click="fullscreen.toggleFullscreen"
    >
      <AppIcon :name="fullscreen.isFullscreen.value ? 'minimize' : 'maximize'" :size="16" />{{
        fullscreen.isFullscreen.value ? 'Vollbild beenden' : 'Vollbild'
      }}
    </button>
    <ClientOnly
      ><PointMap
        ref="map"
        :points="points"
        :selected-id="selected"
        noun="Treffer"
        plural="Treffer"
        title="Karte der Recherchetreffer"
        popup
        research
        embedded
        :popup-content="popupContent"
        @select="emit('select', $event)"
    /></ClientOnly>
    <div
      class="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 px-3 py-1 text-xs text-slate-600"
    >
      <div class="flex flex-wrap items-center gap-x-4 gap-y-1" aria-label="Kartenlegende">
        <span
          v-for="kind in ['event', 'venue', 'organization'] as const"
          :key="kind"
          class="flex items-center gap-1.5"
        >
          <AppIcon
            name="pin"
            :size="16"
            :class="
              kind === 'venue'
                ? 'text-teal-600'
                : kind === 'organization'
                  ? 'text-violet-600'
                  : 'text-blue-600'
            "
          />{{ researchLabels[kind] }}
        </span>
      </div>
      <details>
        <summary class="min-h-11 cursor-pointer content-center">
          {{ points.length }}/{{ items.length }} dieser Seite
        </summary>
        <p class="pb-2">
          Treffer mit Koordinaten auf dieser Ergebnisseite. Nummern entsprechen der Liste. Fehlende
          Koordinaten bleiben unbekannt.
        </p>
      </details>
    </div>
    <p v-if="fullscreen.error.value" role="alert" class="p-3 text-sm">
      {{ fullscreen.error.value }}
    </p>
  </section>
</template>
<style>
@reference '../assets/css/main.css';
.research-map .candidate-map-canvas {
  height: 26rem;
}
.research-map:fullscreen .candidate-map-canvas {
  height: calc(100dvh - 7rem);
  min-height: 320px;
}
.research-map .candidate-map-marker {
  @apply border-blue-600 text-blue-800;
}
.research-map .candidate-map-marker[data-tone='teal'] {
  @apply border-teal-600 text-teal-800;
}
.research-map .candidate-map-marker[data-tone='violet'] {
  @apply border-violet-600 text-violet-800;
}
.research-map .candidate-map-marker[aria-pressed='true'] {
  @apply border-blue-800 bg-blue-600 text-white;
}
.research-popup-content {
  @apply flex items-start gap-3 text-sm text-slate-600;
}
.research-popup-content img {
  @apply h-16 w-14 shrink-0 rounded object-cover;
}
.research-popup-content strong {
  @apply block text-sm text-slate-900;
}
.research-popup-content p {
  margin: 0.3rem 0 !important;
}
.research-popup-content a {
  @apply inline-flex min-h-11 items-center text-blue-700 underline underline-offset-4;
}
.research-map .leaflet-popup-content {
  margin: 12px 16px;
  padding-right: 20px;
}
.research-map .leaflet-popup-close-button {
  width: 44px;
  height: 44px;
  line-height: 44px;
}
@media (min-width: 1280px) {
  .research-map .candidate-map-canvas {
    height: 24rem;
  }
}
</style>
