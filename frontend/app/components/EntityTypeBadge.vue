<script setup lang="ts">
import { entityPresentation } from '~/utils/activity'
defineProps<{ type: string }>()
</script>
<template>
  <span
    class="inline-flex rounded-md px-2 py-0.5 text-xs font-medium"
    :class="entityPresentation(type).tone"
    >{{ entityPresentation(type).label }}</span
  >
</template>
