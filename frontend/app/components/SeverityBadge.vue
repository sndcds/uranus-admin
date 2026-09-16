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
  <span class="inline-flex rounded-md px-2 py-0.5 text-xs font-medium" :class="styles[severity]">{{
    severityLabels[severity]
  }}</span>
</template>
