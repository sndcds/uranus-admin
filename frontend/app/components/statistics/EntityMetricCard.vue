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
    class="statistics-metric"
    :class="{ inactive: !selected }"
    :aria-pressed="selected"
    :aria-label="`${presentation.card}: ${metric(series.total)}`"
    :style="{ '--series-color': presentation.color }"
    @click="$emit('toggle')"
    @pointerenter="$emit('highlight')"
    @pointerleave="$emit('unhighlight')"
    @focus="$emit('highlight')"
    @blur="$emit('unhighlight')"
  >
    <div class="statistics-metric-main">
      <span class="statistics-metric-icon"><AppIcon :name="presentation.icon" :size="22" /></span>
      <div class="min-w-0">
        <span class="statistics-metric-label">{{ presentation.card }}</span
        ><strong>{{ metric(series.total) }}</strong>
      </div>
    </div>
    <div v-if="delta" class="statistics-comparison">
      <span :class="delta.difference < 0 ? 'decrease' : 'increase'"
        >{{ delta.difference < 0 ? '↓' : delta.difference > 0 ? '↑' : '→' }} {{ delta.label }}</span
      >
      <small>gegenüber vorherigem Zeitraum</small>
    </div>
    <span v-else class="statistics-metric-caption">im gewählten Zeitraum</span>
    <EntitySparkline :points="series.points" :color="presentation.color" />
  </button>
</template>
