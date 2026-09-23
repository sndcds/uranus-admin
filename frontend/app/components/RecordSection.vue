<script setup lang="ts">
import { useId } from 'vue'
defineProps<{ title: string; description?: string }>()
const id = useId()
</script>

<template>
  <section class="min-w-0 space-y-3" :aria-labelledby="id">
    <header>
      <h3 :id="id" class="type-section-title">{{ title }}</h3>
      <p v-if="description" class="type-metadata mt-1">{{ description }}</p>
    </header>
    <slot />
  </section>
</template>
