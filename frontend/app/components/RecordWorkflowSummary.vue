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
  <RecordSection title="Qualität & Arbeitsstand">
    <dl class="flex flex-wrap gap-x-10 gap-y-3">
      <div v-if="item.finding_count !== null">
        <dt class="type-metadata">Gespeicherte Befunde ohne behobene</dt>
        <dd class="type-body mt-1 font-semibold">{{ item.finding_count }}</dd>
      </div>
      <div v-if="item.mark_count !== null">
        <dt class="type-metadata">Markierungen einschließlich erledigter</dt>
        <dd class="type-body mt-1 font-semibold">{{ item.mark_count }}</dd>
      </div>
    </dl>
    <p v-if="item.finding_count === null && item.mark_count === null" class="type-body">
      Der Arbeitsstand ist nicht verfügbar.
    </p>
    <NuxtLink :to="findingsHref" class="action-link">Befunde anzeigen</NuxtLink>
  </RecordSection>
</template>
