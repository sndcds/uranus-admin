<script setup lang="ts">
import { computed } from 'vue'
import { graphHref } from '~/utils/graph'
const props = defineProps<{ entityType: string; entityKey: string }>()
const href = computed(() => graphHref(props.entityType, props.entityKey))
</script>
<template>
  <NuxtLink
    v-if="href"
    :to="href"
    class="inline-flex items-center gap-1 rounded text-sm text-fuchsia-700 hover:underline"
  >
    <AppIcon name="graph" :size="14" />Beziehungen anzeigen
  </NuxtLink>
</template>
