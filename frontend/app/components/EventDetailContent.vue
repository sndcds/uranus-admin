<script setup lang="ts">
import { computed } from 'vue'
import type { EntityDetail } from '#shared/contracts'
const props = defineProps<{ data: EntityDetail; loading: boolean }>()
const facts = computed(() =>
  [
    { label: 'Termine insgesamt', value: props.data.item.facts.event_dates },
    { label: 'Standardort', value: props.data.item.facts.venue_name },
    { label: 'Standardraum', value: props.data.item.facts.space_name },
  ].filter((fact) => fact.value !== null && fact.value !== ''),
)
</script>

<template>
  <RecordSection v-if="facts.length" title="Auf einen Blick">
    <dl class="grid gap-4 sm:grid-cols-3">
      <div v-for="fact in facts" :key="fact.label" class="min-w-0">
        <dt class="type-metadata">{{ fact.label }}</dt>
        <dd class="type-body mt-1 break-words font-semibold">{{ fact.value }}</dd>
      </div>
    </dl>
  </RecordSection>
  <RecordSection v-if="data.item.facts.description?.trim()" title="Beschreibung">
    <MarkdownContent :source="data.item.facts.description" />
  </RecordSection>
  <RecordRelations :data="data" :loading="loading" data-event-relations>
    <template #description>
      Gemeinsame Liste nach Objektart und Name, keine chronologische Terminliste.
    </template>
  </RecordRelations>
  <RecordWorkflowSummary :item="data.item" />
</template>
