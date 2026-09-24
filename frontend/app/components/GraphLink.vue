<script setup lang="ts">
import { computed } from 'vue'
import { graphHref } from '~/utils/graph'
const props = defineProps<{
  entityType: string
  entityKey: string
  variant?: 'action' | 'compact'
}>()
const href = computed(() => graphHref(props.entityType, props.entityKey))
</script>
<template>
  <NuxtLink
    v-if="href"
    :to="href"
    :class="variant === 'compact' ? 'button button-compact' : 'action-link'"
  >
    <AppIcon name="graph" :size="14" />Beziehungen
  </NuxtLink>
</template>
