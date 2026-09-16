<script setup lang="ts">
withDefaults(defineProps<{ as?: 'div' | 'ul' | 'section' }>(), { as: 'div' })
</script>

<template>
  <component :is="as" class="data-list"><slot /></component>
</template>
