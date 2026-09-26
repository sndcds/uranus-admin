<script setup lang="ts">
import type { ResearchRecord } from '#shared/contracts'
import { researchLabels, researchStatuses } from '~/utils/research'
defineProps<{ item: Pick<ResearchRecord, 'entity_type' | 'categories' | 'status'> }>()
</script>
<template>
  <StatusBadge class="research-type" :label="researchLabels[item.entity_type]" />
  <StatusBadge
    v-for="category in item.categories"
    :key="category.id"
    class="research-category"
    :label="category.name"
  />
  <StatusBadge
    v-if="item.status"
    :label="researchStatuses[item.status]"
    :tone="
      item.status === 'released' ? 'success' : item.status === 'cancelled' ? 'error' : 'warning'
    "
  />
</template>
