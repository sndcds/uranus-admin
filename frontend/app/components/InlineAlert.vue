<script setup lang="ts">
withDefaults(
  defineProps<{ tone?: 'info' | 'warning' | 'error' | 'success'; compact?: boolean }>(),
  { tone: 'info' },
)
const tones = {
  info: 'border-slate-200 bg-slate-100 text-slate-700',
  warning: 'border-amber-200 bg-amber-50 text-amber-950',
  error: 'border-rose-200 bg-rose-50 text-rose-900',
  success: 'border-emerald-200 bg-emerald-50 text-emerald-900',
}
</script>
<template>
  <div
    :role="tone === 'error' || tone === 'warning' ? 'alert' : 'status'"
    class="text-sm"
    :class="[tones[tone], compact ? 'rounded-lg border-l-2 px-3 py-1' : 'rounded-2xl border p-4']"
  >
    <slot />
  </div>
</template>
