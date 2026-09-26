<script setup lang="ts">
import { computed } from 'vue'
import { inspectorHref } from '~/utils/inspector'
const props = defineProps<{ entityType: string; entityKey: string; timeline?: boolean }>()
const href = computed(() => inspectorHref(props.entityType, props.entityKey))
</script>
<template>
  <NuxtLink v-if="href" :to="href + (timeline ? '#activity' : '')" class="action-link text-xs">
    <AppIcon :name="timeline ? 'history' : 'search'" :size="14" />{{
      timeline ? 'Aktivität zum Datensatz' : 'Datensatz untersuchen'
    }}
  </NuxtLink>
</template>
