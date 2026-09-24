<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import CopyValueButton from './CopyValueButton.vue'
import AppIcon from './AppIcon.vue'
import {
  hasOperationValue,
  operationValue,
  operationTones,
  type TechnicalFact,
} from '~/utils/operations'
const props = withDefaults(
  defineProps<{ items: readonly TechnicalFact[]; title?: string; showTitle?: boolean }>(),
  { title: 'Technische Informationen', showTitle: true },
)
const id = useId()
const visible = computed(() => props.items.filter((item) => hasOperationValue(item.value)))
const copyRevision = ref(0)
watch(
  () => props.items,
  () => {
    copyRevision.value++
  },
  { deep: true, flush: 'sync' },
)
</script>

<template>
  <section
    v-if="visible.length"
    class="operations-techbar"
    :aria-labelledby="showTitle ? id : undefined"
    :aria-label="showTitle ? undefined : title"
  >
    <header v-if="showTitle" class="operations-panel-header">
      <h3 :id="id" class="flex items-center gap-2 text-sm font-semibold">
        <AppIcon name="database" :size="16" />{{ title }}
      </h3>
    </header>
    <dl class="grid min-w-0 gap-3 p-3 sm:grid-cols-2 xl:flex xl:flex-wrap">
      <div
        v-for="item in visible"
        :key="item.label"
        class="min-w-0 xl:flex-1 xl:basis-40 xl:border-l xl:border-slate-200 xl:pl-3 xl:first:border-0 xl:first:pl-0"
      >
        <dt class="operations-meta break-words">{{ item.label }}</dt>
        <dd
          class="flex min-w-0 flex-wrap items-center gap-x-2 text-xs leading-5"
          :class="operationTones[item.tone ?? 'neutral']"
        >
          <time
            v-if="item.datetime"
            :datetime="item.datetime"
            :title="item.timezone"
            class="min-w-0 break-words"
            >{{ operationValue(item.value) }}</time
          >
          <component
            v-else
            :is="item.mono ? 'code' : 'span'"
            class="min-w-0 break-words [overflow-wrap:anywhere]"
            >{{ operationValue(item.value) }}</component
          >
          <CopyValueButton
            v-if="item.copyable"
            :value="operationValue(item.value)"
            :label="item.label"
            :success-message="`${item.label} kopiert.`"
            :reset-key="copyRevision"
          />
          <span v-if="item.timezone" class="operations-meta">{{ item.timezone }}</span>
          <span v-if="item.description || item.metadata" class="operations-meta basis-full">{{
            item.description || item.metadata
          }}</span>
        </dd>
      </div>
    </dl>
  </section>
</template>
