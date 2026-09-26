<script setup lang="ts">
import type { ResearchRecord } from '#shared/contracts'
import { researchKey, researchLabels, researchHref } from '~/utils/research'
const props = defineProps<{ items: ResearchRecord[]; selected: string }>()
const emit = defineEmits<{ select: [id: string] }>()
const panel = ref<HTMLElement | null>(null)
const fullscreen = useFullscreen(panel)
const points = computed(() =>
  props.items.flatMap((item, index) =>
    item.location
      ? [
          {
            id: researchKey(item),
            rank: index + 1,
            display_name: `${researchLabels[item.entity_type]}: ${item.name}${item.event_count === null ? '' : ` · ${item.event_count} Veranstaltungen im Filter`}`,
            ...item.location,
          },
        ]
      : [],
  ),
)
const selectedItem = computed(() =>
  props.items.find((item) => researchKey(item) === props.selected),
)
</script>
<template>
  <section
    ref="panel"
    class="research-map panel min-w-0 space-y-2 bg-white p-2"
    aria-label="Recherche-Karte"
  >
    <div class="flex flex-wrap items-center justify-between gap-2 p-1">
      <p class="type-metadata">
        {{ points.length }} von {{ items.length }} Treffern dieser Seite mit Koordinaten
      </p>
      <button
        v-if="fullscreen.isSupported.value"
        class="button"
        @click="fullscreen.toggleFullscreen"
      >
        <AppIcon :name="fullscreen.isFullscreen.value ? 'minimize' : 'maximize'" />{{
          fullscreen.isFullscreen.value ? 'Vollbild beenden' : 'Vollbild'
        }}
      </button>
    </div>
    <ClientOnly
      ><PointMap
        :points="points"
        :selected-id="selected"
        noun="Treffer"
        plural="Treffer"
        title="Karte der Recherchetreffer"
        popup
        embedded
        @select="emit('select', $event)"
    /></ClientOnly>
    <div v-if="selectedItem" class="space-y-1 p-2">
      <p class="type-row-title">{{ selectedItem.name }}</p>
      <p class="type-metadata">{{ selectedItem.address || selectedItem.city }}</p>
      <NuxtLink
        :to="researchHref(selectedItem.entity_type, selectedItem.entity_key)"
        class="action-link"
        >Details anzeigen →</NuxtLink
      >
    </div>
    <p class="type-metadata p-1">
      Nummern entsprechen der Ergebnisliste. Fehlende Koordinaten bleiben unbekannt.
    </p>
    <p v-if="fullscreen.error.value" role="alert" class="type-metadata">
      {{ fullscreen.error.value }}
    </p>
  </section>
</template>

<style scoped>
.research-map:fullscreen :deep(.candidate-map-canvas) {
  height: calc(100dvh - 20rem);
  min-height: 320px;
}
</style>
