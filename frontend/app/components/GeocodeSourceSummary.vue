<script setup lang="ts">
import GraphLink from './GraphLink.vue'
import { computed } from 'vue'
import type { GeocodeRequestDetail } from '#shared/contracts'
import { geocodeStatuses } from '~/utils/geocoding'
const props = defineProps<{ suggestion: GeocodeRequestDetail }>()
const entityHref = computed(
  () =>
    `/${props.suggestion.entity_type === 'organization' ? 'organizations' : 'venues'}/${props.suggestion.entity_key}`,
)
</script>

<template>
  <RecordSection
    :title="suggestion.entity_name"
    class="border-b border-slate-200 pb-4"
    data-geocode-source
  >
    <div class="flex flex-wrap items-center gap-2">
      <EntityTypeBadge :type="suggestion.entity_type" />
      <StatusBadge :label="geocodeStatuses[suggestion.status]" />
    </div>
    <p class="type-body break-words">
      <span class="sr-only">Quelladresse: </span
      >{{ suggestion.source_address || 'Keine Adresse vorhanden' }}
    </p>
    <div class="flex flex-wrap items-center gap-x-5" role="group" aria-label="Datensatzaktionen">
      <NuxtLink :to="entityHref" class="action-link">{{
        suggestion.entity_type === 'organization' ? 'Organisation öffnen' : 'Ort öffnen'
      }}</NuxtLink>
      <GraphLink :entity-type="suggestion.entity_type" :entity-key="suggestion.entity_key" />
      <EntityInspectorLink
        :entity-type="suggestion.entity_type"
        :entity-key="suggestion.entity_key"
      />
      <NuxtLink
        :to="{
          path: '/marks',
          query: {
            entity_type: suggestion.entity_type,
            entity_key: suggestion.entity_key,
            status: 'all',
          },
        }"
        class="action-link"
        >Markierungen &amp; Notizen</NuxtLink
      >
    </div>
  </RecordSection>
</template>
