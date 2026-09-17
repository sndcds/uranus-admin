<script setup lang="ts">
import { computed } from 'vue'
import type { StatisticsSeries } from '#shared/contracts'
import { statisticsTypes, statisticsDelta } from '~/utils/statistics'
import { metric } from '~/utils/presentation'
import AppIcon from '~/components/AppIcon.vue'
import EntitySparkline from './EntitySparkline.vue'
const props = defineProps<{ series: StatisticsSeries; selected: boolean }>()
defineEmits<{ toggle: []; highlight: []; unhighlight: [] }>()
const presentation = computed(() => statisticsTypes[props.series.entity_type])
const delta = computed(() =>
  props.series.previous_total === null
    ? null
    : statisticsDelta(props.series.total, props.series.previous_total),
)
</script>
<template>
  <button
    class="statistics-metric panel p-4 text-left hover:border-fuchsia-300"
    :class="{ 'opacity-50 border-dashed': !selected }"
    :aria-pressed="selected"
    :aria-label="`${presentation.card}: ${metric(series.total)}`"
    :style="{ '--series-color': presentation.color }"
    @click="$emit('toggle')"
    @pointerenter="$emit('highlight')"
    @pointerleave="$emit('unhighlight')"
    @focus="$emit('highlight')"
    @blur="$emit('unhighlight')"
  >
    <div class="statistics-metric-main flex items-start gap-3">
      <span
        class="statistics-metric-icon grid h-10 w-10 shrink-0 place-items-center rounded-xl"
        :style="{
          color: presentation.color,
          background: `color-mix(in srgb, ${presentation.color} 10%, white)`,
        }"
        ><AppIcon :name="presentation.icon" :size="22"
      /></span>
      <div class="min-w-0">
        <span class="statistics-metric-label block text-xs text-slate-600">{{
          presentation.card
        }}</span
        ><strong class="block text-xl font-semibold tabular-nums">{{
          metric(series.total)
        }}</strong>
      </div>
    </div>
    <div v-if="delta" class="statistics-comparison mt-2 text-xs">
      <span
        :class="
          delta.difference < 0
            ? 'rounded-md bg-rose-50 px-2 py-0.5 text-rose-700'
            : 'rounded-md bg-emerald-50 px-2 py-0.5 text-emerald-700'
        "
        >{{ delta.difference < 0 ? '↓' : delta.difference > 0 ? '↑' : '→' }} {{ delta.label }}</span
      >
      <small class="mt-1 block text-xs text-slate-500">gegenüber vorherigem Zeitraum</small>
    </div>
    <span v-else class="statistics-metric-caption mt-2 block text-xs text-slate-500"
      >im gewählten Zeitraum</span
    >
    <EntitySparkline :points="series.points" :color="presentation.color" />
  </button>
</template>
