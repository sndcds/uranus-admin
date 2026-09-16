<script setup lang="ts">
import { metric } from '~/utils/presentation'
defineProps<{
  label: string
  value?: number | null
  description: string
  tone?: 'rose' | 'fuchsia'
  to?: string
}>()
</script>

<template>
  <div class="card p-5" :class="tone === 'rose' ? 'border-rose-200' : ''">
    <div class="flex items-center justify-between gap-2">
      <span class="text-sm font-medium text-slate-500">{{ label }}</span
      ><span
        v-if="tone"
        aria-hidden="true"
        :class="tone === 'rose' ? 'text-rose-500' : 'text-fuchsia-600'"
        >●</span
      >
    </div>
    <div
      class="mt-3 font-black"
      :class="[
        value == null ? 'text-lg leading-9 text-slate-500' : 'text-3xl',
        tone === 'rose' && value != null ? 'text-rose-600' : '',
      ]"
    >
      {{ metric(value) }}
    </div>
    <p class="mt-2 text-xs leading-5 text-slate-500">{{ description }}</p>
    <NuxtLink
      v-if="to"
      :to="to"
      :aria-label="`${label} öffnen`"
      class="mt-2 inline-block text-xs font-semibold text-fuchsia-700"
      >Öffnen →</NuxtLink
    >
  </div>
</template>
