<script setup lang="ts">
import { computed } from 'vue'
import type { EntityDetail } from '#shared/contracts'
const props = defineProps<{ item: EntityDetail['item'] }>()
const findingsHref = computed(() => ({
  path: '/findings',
  query: {
    mode: 'persisted',
    entity_type: props.item.entity_type,
    entity_key: props.item.entity_key,
  },
}))
</script>

<template>
  <RecordSection title="Qualität & Arbeitsstand" surface="subtle">
    <template #actions>
      <NuxtLink :to="findingsHref" class="button button-compact">Befunde öffnen</NuxtLink>
    </template>
    <CompactFacts
      :items="[
        { label: 'Gespeicherte Befunde', value: item.finding_count, description: 'Ohne behobene' },
        { label: 'Markierungen', value: item.mark_count, description: 'Einschließlich erledigter' },
      ]"
      missing="omit"
    />
    <p v-if="item.finding_count === null && item.mark_count === null" class="type-body">
      Der Arbeitsstand ist nicht verfügbar.
    </p>
  </RecordSection>
</template>
