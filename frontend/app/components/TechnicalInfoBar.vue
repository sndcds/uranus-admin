<script setup lang="ts">
import { computed, onBeforeUnmount, ref, useId, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import {
  hasOperationValue,
  operationValue,
  operationTones,
  type TechnicalFact,
} from '~/utils/operations'
const props = withDefaults(defineProps<{ items: readonly TechnicalFact[]; title?: string }>(), {
  title: 'Technische Informationen',
})
const id = useId()
const visible = computed(() => props.items.filter((item) => hasOperationValue(item.value)))
const feedback = ref('')
let revision = 0
watch(
  () => props.items,
  () => {
    revision++
    feedback.value = ''
  },
  { deep: true, flush: 'sync' },
)
onBeforeUnmount(() => {
  revision++
})
async function copy(item: TechnicalFact) {
  const current = ++revision
  feedback.value = ''
  try {
    await navigator.clipboard.writeText(operationValue(item.value))
    if (current === revision) feedback.value = `${item.label} kopiert.`
  } catch {
    if (current === revision)
      feedback.value = 'Kopieren nicht verfügbar. Der Wert kann als Text ausgewählt werden.'
  }
}
</script>

<template>
  <section v-if="visible.length" class="technical-bar" :aria-labelledby="id">
    <header class="operations-panel-header">
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
          <component
            :is="item.mono ? 'code' : 'span'"
            class="min-w-0 break-words [overflow-wrap:anywhere]"
            >{{ operationValue(item.value) }}</component
          >
          <button
            v-if="item.copyable"
            type="button"
            class="action-link text-xs"
            :aria-label="`${item.label} kopieren`"
            @click="copy(item)"
          >
            <AppIcon name="copy" :size="14" />Kopieren
          </button>
          <span v-if="item.metadata" class="operations-meta basis-full">{{ item.metadata }}</span>
        </dd>
      </div>
    </dl>
    <p role="status" class="operations-meta px-3" :class="feedback ? 'pb-3' : 'sr-only'">
      {{ feedback }}
    </p>
  </section>
</template>
