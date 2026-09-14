<script setup lang="ts">
import { severityLabels } from '~/utils/presentation'
import type { Severity } from '#shared/contracts'
defineProps<{ severity: Severity }>()
const styles: Record<Severity, string> = {
  error: 'bg-rose-50 text-rose-800',
  warning: 'bg-amber-50 text-amber-900',
  info: 'bg-sky-50 text-sky-800',
}
</script>

<template>
  <span
    class="inline-flex rounded-full px-2 py-1 text-xs font-semibold"
    :class="styles[severity]"
    >{{ severityLabels[severity] }}</span
  >
</template>
