<script setup lang="ts">
import { computed } from 'vue'
import type { StatisticsSeries } from '#shared/contracts'
import { statisticsTypes, statisticsDelta } from '~/utils/statistics'
import { metric } from '~/utils/presentation'
import AppIcon from '~/components/AppIcon.vue'
import EntitySparkline from './EntitySparkline.vue'
const props = defineProps<{ series: StatisticsSeries; selected: boolean; showScope?: boolean }>()
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
    class="statistics-metric analytics-kpi text-left hover:bg-slate-50"
    :class="{ 'statistics-metric-hidden': !selected }"
    :aria-pressed="selected"
    :aria-label="`${presentation.card}: ${metric(series.total)}`"
    :style="{ '--series-color': presentation.color }"
    @click="$emit('toggle')"
    @pointerenter="$emit('highlight')"
    @pointerleave="$emit('unhighlight')"
    @focus="$emit('highlight')"
    @blur="$emit('unhighlight')"
  >
    <div class="statistics-metric-main flex items-start gap-2">
      <span
        class="statistics-metric-icon grid h-7 w-7 shrink-0 place-items-center rounded-md"
        :style="{
          color: presentation.color,
          background: `color-mix(in srgb, ${presentation.color} 10%, white)`,
        }"
        ><AppIcon :name="presentation.icon" :size="16"
      /></span>
      <div class="min-w-0">
        <span class="statistics-metric-label block text-xs text-slate-600">{{
          presentation.card
        }}</span
        ><strong class="block text-lg font-semibold tabular-nums">{{
          metric(series.total)
        }}</strong>
      </div>
    </div>
    <div v-if="delta" class="statistics-comparison mt-2 text-xs">
      <span class="font-semibold text-slate-700"
        >{{ delta.difference < 0 ? '↓' : delta.difference > 0 ? '↑' : '→' }} {{ delta.label }}</span
      >
      <small class="mt-1 block text-xs text-slate-500">gegenüber vorherigem Zeitraum</small>
    </div>
    <span v-else class="statistics-metric-caption mt-2 block text-xs text-slate-500"
      >im gewählten Zeitraum</span
    >
    <span v-if="showScope" class="block text-xs font-semibold">{{
      series.scope === 'geo' ? 'Gebiet' : 'Systemweit'
    }}</span>
    <span class="sr-only">{{ selected ? 'Serie eingeblendet' : 'Serie ausgeblendet' }}</span>
    <EntitySparkline :points="series.points" :color="presentation.color" />
  </button>
</template>
