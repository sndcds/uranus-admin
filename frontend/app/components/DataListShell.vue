<script setup lang="ts">
withDefaults(defineProps<{ as?: 'div' | 'ul' | 'section'; dense?: boolean }>(), { as: 'div' })
</script>

<template>
  <component :is="as" class="data-list" :class="{ 'data-list-dense': dense }"><slot /></component>
</template>
