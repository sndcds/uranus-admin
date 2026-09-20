<script setup lang="ts">
defineProps<{ sql: string }>()
</script>
<template>
  <div>
    <h3 class="font-semibold">SQL</h3>
    <pre
      class="overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-100"
    ><code>{{ sql }}</code></pre>
  </div>
</template>
