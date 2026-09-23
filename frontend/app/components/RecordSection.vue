<script setup lang="ts">
import { useId } from 'vue'
withDefaults(
  defineProps<{
    title: string
    description?: string
    surface?: 'plain' | 'panel' | 'subtle' | 'table'
  }>(),
  { surface: 'plain', description: undefined },
)
const id = useId()
</script>

<template>
  <section :class="`section-${surface}`" :aria-labelledby="id">
    <header :class="surface === 'plain' ? undefined : 'operations-panel-header'">
      <div class="min-w-0">
        <h3 :id="id" class="type-section-title flex items-center gap-2">
          <slot name="icon" />{{ title }}
        </h3>
        <p v-if="description" class="type-metadata mt-1">{{ description }}</p>
      </div>
      <div v-if="$slots.actions" class="flex flex-wrap items-center gap-2">
        <slot name="actions" />
      </div>
    </header>
    <div
      :class="
        surface === 'panel' || surface === 'subtle'
          ? 'space-y-3 p-operations-panel'
          : surface === 'plain'
            ? 'space-y-3'
            : undefined
      "
    >
      <slot />
    </div>
  </section>
</template>
