<script setup lang="ts">
withDefaults(defineProps<{ tone?: 'info' | 'warning' | 'error' | 'success' }>(), { tone: 'info' })
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
    class="rounded-2xl border p-4 text-sm"
    :class="tones[tone]"
  >
    <slot />
  </div>
</template>
