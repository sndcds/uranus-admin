<script setup lang="ts">
withDefaults(defineProps<{ label: string; tone?: 'neutral' | 'error' | 'warning' | 'success' }>(), {
  tone: 'neutral',
})
const tones = {
  neutral: 'bg-slate-100 text-slate-600',
  error: 'bg-rose-50 text-rose-700',
  warning: 'bg-amber-50 text-amber-800',
  success: 'bg-emerald-50 text-emerald-700',
}
</script>
<template>
  <span
    class="inline-flex max-w-full break-words rounded-md px-2 py-0.5 text-xs font-medium"
    :class="tones[tone]"
    >{{ label }}</span
  >
</template>
