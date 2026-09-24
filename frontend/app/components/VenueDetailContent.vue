<script setup lang="ts">
import type { EntityDetail } from '#shared/contracts'
defineProps<{ data: EntityDetail; loading: boolean }>()
</script>

<template>
  <div class="operations-grid" data-record-info-grid>
    <RecordSection title="Auf einen Blick" surface="panel">
      <CompactFacts :items="[{ label: 'Räume insgesamt', value: data.item.facts.spaces }]" />
    </RecordSection>
    <RecordLocation :item="data.item" />
  </div>
  <RecordRelations :data="data" :loading="loading" />
  <RecordWorkflowSummary :item="data.item" />
</template>
