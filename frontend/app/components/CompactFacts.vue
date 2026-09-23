<script setup lang="ts">
import { computed } from 'vue'
import {
  hasOperationValue,
  operationValue,
  operationTones,
  type CompactFact,
} from '~/utils/operations'
const props = withDefaults(
  defineProps<{
    items: readonly CompactFact[]
    columns?: 2 | 3 | 4
    missing?: 'omit' | 'label'
  }>(),
  { columns: 2, missing: 'label' },
)
const visible = computed(() =>
  props.items.filter((item) => props.missing !== 'omit' || hasOperationValue(item.value)),
)
const layouts = {
  2: 'sm:grid-cols-2',
  3: 'sm:grid-cols-2 xl:grid-cols-3',
  4: 'sm:grid-cols-2 xl:grid-cols-4',
}
</script>

<template>
  <dl v-if="visible.length" class="grid min-w-0 gap-x-4 gap-y-3" :class="layouts[columns]">
    <div v-for="item in visible" :key="item.label" class="min-w-0">
      <dt class="operations-meta break-words">{{ item.label }}</dt>
      <dd
        class="mt-0.5 break-words text-sm font-semibold [overflow-wrap:anywhere]"
        :class="operationTones[item.tone ?? 'neutral']"
      >
        {{ operationValue(item.value) }}
        <span v-if="item.description || item.metadata" class="operations-meta block font-normal">{{
          item.description || item.metadata
        }}</span>
      </dd>
    </div>
  </dl>
</template>
