<script setup lang="ts">
import { dateTime, metric } from '~/utils/presentation'
withDefaults(
  defineProps<{
    total: number
    visible?: number
    noun: string
    description?: string
    observedAt?: string
    label?: string
  }>(),
  { visible: undefined, label: 'Ergebnisübersicht', description: undefined, observedAt: undefined },
)
</script>
<template>
  <section class="space-y-2" :aria-label="label">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <p class="text-sm font-semibold">{{ metric(total) }} {{ noun }} insgesamt</p>
      <p v-if="description" class="text-xs text-slate-500">{{ description }}</p>
    </div>
    <div class="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-slate-600">
      <span v-if="visible !== undefined" class="font-medium"
        >Auf dieser Seite: {{ visible }} Einträge</span
      ><slot />
    </div>
    <p v-if="observedAt" class="text-xs text-slate-500">
      Stand: {{ dateTime(observedAt) }} · Europe/Berlin
    </p>
  </section>
</template>
