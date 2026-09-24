<script setup lang="ts">
import { markEntityTypeSchema } from '#shared/contracts'
const props = withDefaults(
  defineProps<{ entityType: string; entityKey: string; variant?: 'button' | 'action' }>(),
  { variant: 'button' },
)
const supported = computed(() => markEntityTypeSchema.safeParse(props.entityType).success)
</script>

<template>
  <NuxtLink
    v-if="supported"
    :class="variant === 'action' ? 'action-link' : 'button mt-3'"
    :to="{
      path: '/marks',
      query: { entity_type: entityType, entity_key: entityKey, status: 'all' },
    }"
    >Markierungen &amp; Notizen</NuxtLink
  >
</template>
