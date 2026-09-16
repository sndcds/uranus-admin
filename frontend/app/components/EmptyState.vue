<script setup lang="ts">
defineProps<{ message: string }>()
</script>
<template>
  <p
    class="rounded-2xl border border-dashed border-slate-300 bg-white px-5 py-8 text-center text-sm text-slate-500"
  >
    {{ message }}
  </p>
</template>
