<script setup lang="ts">
import { computed } from 'vue'
import type { EntityDetail } from '#shared/contracts'
const props = defineProps<{ data: EntityDetail; loading: boolean }>()
const facts = computed(() => [
  { label: 'Veranstaltungen', value: props.data.item.facts.events },
  { label: 'Orte', value: props.data.item.facts.venues },
  {
    label: 'Teammitgliedschaften',
    value: props.data.item.facts.memberships,
    description: 'Einschließlich Einladungen',
  },
])
</script>

<template>
  <div class="operations-grid" data-record-info-grid>
    <RecordSection title="Auf einen Blick" surface="panel">
      <CompactFacts :items="facts" :columns="3" />
    </RecordSection>
    <RecordLocation :item="data.item" />
  </div>
  <RecordRelations :data="data" :loading="loading" />
  <RecordWorkflowSummary :item="data.item" />
</template>
