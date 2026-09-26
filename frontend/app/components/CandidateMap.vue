<script setup lang="ts">
import { useTemplateRef } from 'vue'
import PointMap from './PointMap.vue'
import type { GeocodeCandidate } from '#shared/contracts'
defineProps<{ candidates: GeocodeCandidate[]; selectedId: string; embedded?: boolean }>()
defineEmits<{ select: [id: string] }>()
const map = useTemplateRef('map')
defineExpose({ focusCandidate: (id: string, reveal = false) => map.value?.focusPoint(id, reveal) })
</script>
<template>
  <PointMap
    ref="map"
    :points="candidates"
    :selected-id="selectedId"
    :embedded="embedded"
    empty-message="Keine Standortkandidaten vorhanden."
    noun="Kandidat"
    plural="Kandidaten"
    title="Karte der Standortkandidaten"
    @select="$emit('select', $event)"
  />
</template>
