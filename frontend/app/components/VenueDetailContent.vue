<script setup lang="ts">
import type { EntityDetail } from '#shared/contracts'
import { metric } from '~/utils/presentation'
defineProps<{ data: EntityDetail; loading: boolean }>()
</script>

<template>
  <RecordSection title="Auf einen Blick">
    <dl>
      <dt class="type-metadata">Räume insgesamt</dt>
      <dd class="type-body mt-1 font-semibold">{{ metric(data.item.facts.spaces) }}</dd>
    </dl>
  </RecordSection>
  <RecordLocation :item="data.item" />
  <RecordRelations :data="data" :loading="loading" />
  <RecordWorkflowSummary :item="data.item" />
</template>
