<script setup lang="ts">
import type { ResearchRecord, ResearchQuery } from '#shared/contracts'
import { researchHref, researchUrlQuery } from '~/utils/research'
const props = defineProps<{ item: ResearchRecord; selected?: boolean; query?: ResearchQuery }>()
defineEmits<{ select: [] }>()
const date = computed(() =>
  props.item.start_date ? new Date(`${props.item.start_date}T12:00:00Z`) : null,
)
const weekday = computed(() =>
  date.value
    ? new Intl.DateTimeFormat('de-DE', { weekday: 'short', timeZone: 'UTC' })
        .format(date.value)
        .replace('.', '')
    : '',
)
const month = computed(() =>
  date.value
    ? new Intl.DateTimeFormat('de-DE', { month: 'short', timeZone: 'UTC' })
        .format(date.value)
        .replace('.', '')
    : '',
)
</script>
<template>
  <article
    class="research-result flex min-w-0 items-center gap-3 rounded-md border px-3 py-2.5"
    :class="
      selected ? 'border-blue-400 bg-blue-50/60' : 'border-slate-200 bg-white hover:bg-slate-50'
    "
  >
    <div
      v-if="item.entity_type === 'event'"
      class="w-12 shrink-0 border-r border-slate-200 pr-3 text-center text-xs text-slate-600"
    >
      <time v-if="item.start_date" :datetime="item.start_date"
        ><span class="block text-[11px] uppercase">{{ weekday }}</span
        ><span class="block text-xl font-bold leading-7 text-slate-900">{{
          item.start_date.slice(8)
        }}</span
        ><span class="uppercase">{{ month }}</span></time
      >
      <span v-else>Termin offen</span>
    </div>
    <div class="min-w-0 flex-1 space-y-1.5">
      <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
        <NuxtLink
          :to="{
            path: researchHref(item.entity_type, item.entity_key),
            query: researchUrlQuery({ from_date: query?.from_date, to_date: query?.to_date }),
          }"
          class="min-h-11 content-center text-sm font-semibold leading-5 text-blue-950 hover:underline sm:min-h-0 sm:text-base"
          >{{ item.name }}</NuxtLink
        >
        <div class="flex flex-wrap gap-1.5"><ResearchBadges :item="item" /></div>
      </div>
      <div class="flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-600">
        <span v-if="item.venue_name" class="flex items-center gap-2"
          ><AppIcon name="pin" :size="15" class="shrink-0" />{{ item.venue_name }}</span
        >
        <span v-if="item.organization_name" class="flex items-center gap-2"
          ><AppIcon name="organization" :size="15" class="shrink-0" />{{
            item.organization_name
          }}</span
        >
        <span v-if="item.entity_type !== 'event'" class="flex items-center gap-2"
          ><AppIcon name="pin" :size="15" />{{
            item.address || item.city || 'Adresse unbekannt'
          }}</span
        >
      </div>
      <p class="flex items-center gap-2 text-xs text-slate-700">
        <AppIcon :name="item.entity_type === 'event' ? 'clock' : 'calendar'" :size="15" />
        <template v-if="item.entity_type === 'event'">{{
          item.all_day
            ? 'Ganztägig'
            : item.start_time
              ? item.start_time.slice(0, 5) +
                (item.end_time ? ' – ' + item.end_time.slice(0, 5) : '')
              : 'Uhrzeit unbekannt'
        }}</template>
        <template v-else>{{ item.event_count }} Veranstaltungen im Filter</template>
      </p>
    </div>
    <button
      type="button"
      class="research-icon-button -mr-2 shrink-0 text-blue-700"
      :aria-label="`Vorschau: ${item.name}`"
      :aria-pressed="selected"
      @click="$emit('select')"
    >
      <AppIcon name="next" :size="18" />
    </button>
  </article>
</template>
