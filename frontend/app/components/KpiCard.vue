<script setup lang="ts">
import { metric } from '~/utils/presentation'
defineProps<{
  label: string
  value?: number | null
  description: string
  tone?: 'rose' | 'fuchsia'
  to?: string
  compact?: boolean
  valueLabel?: string
  actionLabel?: string
}>()
</script>

<template>
  <div v-if="compact" class="operations-panel flex flex-col p-3" :aria-label="label">
    <div class="flex flex-wrap items-baseline gap-x-2 gap-y-1">
      <div
        class="text-xl font-semibold tabular-nums"
        :class="tone === 'rose' ? 'text-rose-700' : 'text-slate-900'"
      >
        <slot name="value"
          ><span :class="value == null && !valueLabel ? 'text-sm text-slate-500' : undefined">{{
            valueLabel ?? metric(value)
          }}</span></slot
        >
      </div>
      <h4 class="text-xs font-semibold text-slate-700">{{ label }}</h4>
    </div>
    <p class="mt-1 text-xs leading-4 text-slate-600">{{ description }}</p>
    <slot name="meta" />
    <NuxtLink
      v-if="to"
      :to="to"
      :aria-label="actionLabel ?? `${label} öffnen`"
      class="action-link mt-auto text-xs"
    >
      {{ actionLabel ?? `${label} öffnen` }}<AppIcon name="arrow" :size="14" />
    </NuxtLink>
  </div>
  <div v-else class="min-w-0 rounded-2xl border border-slate-200 bg-white p-4">
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
