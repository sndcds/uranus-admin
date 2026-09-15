<script setup lang="ts">
import { markEntityTypeSchema } from '#shared/contracts'
const props = defineProps<{ entityType: string; entityKey: string }>()
const supported = computed(() => markEntityTypeSchema.safeParse(props.entityType).success)
</script>

<template>
  <NuxtLink
    v-if="supported"
    class="button mt-3"
    :to="{
      path: '/marks',
      query: { entity_type: entityType, entity_key: entityKey, status: 'all' },
    }"
    >Markierungen &amp; Notizen</NuxtLink
  >
</template>
