<script setup lang="ts">
import type { ResearchRecord, ResearchQuery } from '#shared/contracts'
import {
  researchDate,
  researchHref,
  researchLabels,
  researchStatuses,
  researchUrlQuery,
} from '~/utils/research'
defineProps<{ item: ResearchRecord; selected?: boolean; query?: ResearchQuery }>()
defineEmits<{ select: [] }>()
</script>
<template>
  <article
    class="panel flex min-w-0 gap-3 p-3 sm:p-4"
    :class="selected ? 'border-fuchsia-400 bg-fuchsia-50/30' : ''"
  >
    <div
      v-if="item.entity_type === 'event'"
      class="w-16 shrink-0 border-r border-slate-200 pr-3 text-center text-xs text-slate-600"
    >
      <template v-if="item.start_date"
        ><span class="block text-xl font-bold text-slate-900">{{ item.start_date.slice(8) }}</span
        >{{ researchDate(item.start_date).slice(3) }}</template
      ><span v-else>Termin offen</span>
    </div>
    <div class="min-w-0 flex-1 space-y-2">
      <div class="flex flex-wrap items-start gap-2">
        <NuxtLink
          :to="{
            path: researchHref(item.entity_type, item.entity_key),
            query: researchUrlQuery({ from_date: query?.from_date, to_date: query?.to_date }),
          }"
          class="type-row-title hover:underline"
          >{{ item.name }}</NuxtLink
        ><StatusBadge :label="researchLabels[item.entity_type]" /><StatusBadge
          v-for="category in item.categories"
          :key="category.id"
          :label="category.name"
        /><StatusBadge
          v-if="item.status"
          :label="researchStatuses[item.status]"
          :tone="
            item.status === 'released'
              ? 'success'
              : item.status === 'cancelled'
                ? 'error'
                : 'warning'
          "
        />
      </div>
      <div class="flex flex-wrap gap-x-4 gap-y-1 type-metadata">
        <span v-if="item.venue_name">{{ item.venue_name }}</span
        ><span v-if="item.organization_name">{{ item.organization_name }}</span
        ><span v-if="item.entity_type !== 'event'">{{
          item.address || item.city || 'Adresse unbekannt'
        }}</span>
      </div>
      <p class="type-metadata">
        <template v-if="item.entity_type === 'event'">{{
          item.all_day
            ? 'Ganztägig'
            : item.start_time
              ? item.start_time.slice(0, 5) +
                (item.end_time ? ' – ' + item.end_time.slice(0, 5) : '')
              : 'Uhrzeit unbekannt'
        }}</template
        ><template v-else>{{ item.event_count }} Veranstaltungen im Filter</template>
      </p>
    </div>
    <button
      type="button"
      class="button shrink-0 self-center px-2"
      :aria-label="`Vorschau: ${item.name}`"
      :aria-pressed="selected"
      @click="$emit('select')"
    >
      <AppIcon name="next" />
    </button>
  </article>
</template>
