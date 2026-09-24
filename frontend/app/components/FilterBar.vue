<script setup lang="ts">
withDefaults(defineProps<{ compact?: boolean; columns?: 2 | 3 | 4; stackActions?: boolean }>(), {
  columns: 4,
})
defineEmits<{ apply: [] }>()
</script>
<template>
  <form
    class="border border-slate-200 bg-white [&_label]:min-w-0 [&_select]:w-full [&_input]:w-full"
    :class="compact ? 'rounded-xl p-3' : 'rounded-2xl p-4'"
    aria-label="Filter"
    @submit.prevent="$emit('apply')"
  >
    <div
      class="grid items-end gap-3 sm:grid-cols-2"
      :class="
        compact && $slots.actions && !stackActions
          ? columns === 2
            ? 'xl:grid-cols-[repeat(2,minmax(0,1fr))_auto]'
            : columns === 3
              ? 'xl:grid-cols-[repeat(3,minmax(0,1fr))_auto]'
              : 'xl:grid-cols-[repeat(4,minmax(0,1fr))_auto]'
          : 'xl:grid-cols-4'
      "
    >
      <slot />
      <div
        v-if="$slots.actions"
        class="flex flex-wrap items-center gap-2 sm:col-span-2"
        :class="stackActions ? 'xl:col-span-full' : 'xl:col-span-1'"
      >
        <slot name="actions" />
      </div>
    </div>
    <slot name="help" />
  </form>
</template>
