<script setup lang="ts">
defineProps<{ items: { label: string; value: string | number | boolean | null }[] }>()
</script>
<template>
  <dl class="panel grid gap-4 p-4 sm:grid-cols-2 sm:p-5">
    <template v-for="item in items" :key="item.label">
      <div v-if="item.value !== null" class="min-w-0">
        <dt class="text-xs text-slate-500">{{ item.label }}</dt>
        <dd class="mt-1 whitespace-pre-wrap break-words text-sm text-slate-900">
          {{ typeof item.value === 'boolean' ? (item.value ? 'Ja' : 'Nein') : item.value }}
        </dd>
      </div>
    </template>
  </dl>
</template>
