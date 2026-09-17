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
  <div class="min-w-0 rounded-2xl border border-slate-200 bg-white p-4">
    <div class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
      <strong
        class="tabular-nums"
        :class="[
          value == null ? 'text-sm text-slate-500' : 'text-xl',
          tone === 'rose' && value != null ? 'text-rose-700' : '',
        ]"
        >{{ metric(value) }}</strong
      >
      <span class="text-sm font-semibold">{{ label }}</span>
      <NuxtLink
        v-if="to"
        :to="to"
        :aria-label="`${label} öffnen`"
        class="ml-auto rounded text-fuchsia-700"
        ><AppIcon name="arrow" :size="16" />
      </NuxtLink>
    </div>
    <p class="mt-1 text-xs leading-5 text-slate-500">{{ description }}</p>
  </div>
</template>
