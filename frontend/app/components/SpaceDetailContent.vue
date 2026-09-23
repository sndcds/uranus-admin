<script setup lang="ts">
import type { EntityDetail } from '#shared/contracts'
defineProps<{ data: EntityDetail; loading: boolean }>()
</script>

<template>
  <!-- The space's only verified facts (venue and organization) are its hero context. -->
  <RecordRelations :data="data" :loading="loading" />
  <RecordWorkflowSummary :item="data.item" />
</template>
