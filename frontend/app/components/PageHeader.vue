<script setup lang="ts">
import SqlProvenanceButton from './sql/SqlProvenanceButton.vue'
defineProps<{
  title: string
  description?: string
  titleId?: string
  record?: boolean
  stackActions?: boolean
  compactActions?: boolean
}>()
</script>
<template>
  <header
    class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between"
    :class="{ 'operations-header': stackActions }"
  >
    <div class="flex min-w-0 flex-1 gap-3" :class="record ? 'flex-row' : 'flex-col sm:flex-row'">
      <slot name="leading" />
      <div class="min-w-0">
        <div class="flex flex-wrap items-center gap-2">
          <h2
            :id="titleId"
            class="min-w-0 max-w-full"
            :class="record ? 'type-record-title' : 'type-page-title'"
          >
            {{ title }}
          </h2>
          <slot name="badge" />
        </div>
        <p v-if="description" class="mt-1 text-sm leading-5 text-slate-600">{{ description }}</p>
        <slot name="context" />
      </div>
    </div>
    <div
      data-page-header-actions
      class="flex w-full min-w-0 gap-2 sm:w-auto sm:flex-row sm:flex-wrap sm:items-center sm:justify-end"
      :class="compactActions ? 'flex-row flex-wrap items-center' : 'flex-col'"
    >
      <div class="flex empty:hidden" :class="compactActions ? 'order-1' : 'order-2 sm:order-1'">
        <SqlProvenanceButton />
      </div>
      <div
        data-page-header-primary-actions
        class="flex min-w-0 flex-wrap items-center gap-2 empty:hidden"
        :class="compactActions ? 'order-2' : 'order-1 sm:order-2'"
      >
        <slot name="actions"><slot /></slot>
      </div>
    </div>
  </header>
</template>

<style scoped>
/* Opt-in: keep the record identity readable beside a full operations toolbar. */
@media (min-width: 640px) and (max-width: 1100px) {
  .operations-header {
    flex-direction: column;
  }
  .operations-header > [data-page-header-actions] {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
