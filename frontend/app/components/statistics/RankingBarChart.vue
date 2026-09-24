<script setup lang="ts">
import { useId } from 'vue'
import type { EventContentRanking } from '#shared/contracts'
import { metric } from '~/utils/presentation'
defineProps<{ title: string; ranking: EventContentRanking; totalEvents: number }>()
const titleId = useId()
const percentage = (value: number) =>
  new Intl.NumberFormat('de-DE', { maximumFractionDigits: 2 }).format(value)
</script>
<template>
  <section class="section-panel min-w-0 p-3" :aria-labelledby="titleId">
    <h3 :id="titleId" class="type-section-title">{{ title }}</h3>
    <p class="mt-1 text-xs text-slate-500">
      {{ metric(ranking.distinct_assignment_count) }} verschiedene Zuordnungen ·
      {{ ranking.items.length }} davon angezeigt
    </p>
    <ol v-if="ranking.items.length" class="mt-3 space-y-3" :aria-label="title">
      <li v-for="item in ranking.items" :key="item.id" class="min-w-0">
        <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm">
          <span class="min-w-0 break-words font-medium [overflow-wrap:anywhere]"
            >{{ item.rank }}. {{ item.name }}</span
          >
          <span class="tabular-nums"
            >{{ metric(item.event_count) }} Events ·
            {{ percentage(item.event_share_percent) }} %</span
          >
        </div>
        <div
          class="mt-1 h-2 overflow-hidden rounded bg-slate-100"
          aria-hidden="true"
          :title="`${item.event_count} von ${totalEvents} Events · ${percentage(item.event_share_percent)} %`"
        >
          <div
            class="h-full rounded bg-fuchsia-600"
            :style="{ width: `${item.event_share_percent}%` }"
          />
        </div>
        <p class="sr-only">{{ item.event_count }} von {{ totalEvents }} Events</p>
        <p v-if="item.previous_event_count !== null" class="mt-1 text-xs text-slate-600">
          <template v-if="item.previous_rank === null">Neu im Ranking</template>
          <template v-else-if="item.rank_delta === 0">Rang unverändert</template>
          <template v-else
            >Rang {{ item.rank_delta! > 0 ? '↑' : '↓' }} {{ Math.abs(item.rank_delta!) }}</template
          >
          · {{ item.count_delta! > 0 ? '+' : '' }}{{ metric(item.count_delta) }} Events ·
          {{ item.share_delta_percentage_points! > 0 ? '+' : ''
          }}{{ percentage(item.share_delta_percentage_points!) }} Prozentpunkte
        </p>
      </li>
    </ol>
    <p v-else class="mt-3 text-sm text-slate-500">
      Keine Zuordnungen im gewählten Erstellungszeitraum.
    </p>
  </section>
</template>
