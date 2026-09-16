<script setup lang="ts">
import { computed } from 'vue'
import type { ActivityItem } from '~/utils/activity'
import { activityTypes, activityName, activityStatus } from '~/utils/activity'
import { activityTime, dateTime, adminTimeZone } from '~/utils/presentation'
const props = defineProps<{ item: ActivityItem; observedAt: string; grouped?: boolean }>()
const presentation = computed(() => activityTypes[props.item.entity_type])
const name = computed(() => activityName(props.item))
const status = computed(() => activityStatus(props.item.status))
</script>

<template>
  <li
    class="grid min-w-0 grid-cols-[4rem_minmax(0,1fr)] gap-x-3 gap-y-2 px-4 py-3 transition-colors hover:bg-slate-50 sm:px-5 md:grid-cols-[5rem_minmax(0,1fr)_auto_7rem]"
  >
    <ActivityThumbnail :item="item" />
    <div class="min-w-0">
      <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
        <component
          :is="grouped ? 'h4' : 'h3'"
          class="min-w-0 break-words text-sm font-semibold text-slate-900"
          :title="item.entity_name"
        >
          {{ name }}
        </component>
        <span
          class="inline-flex rounded-md px-2 py-0.5 text-[11px] font-medium"
          :class="presentation.tone"
          >{{ presentation.label }}</span
        >
      </div>
      <p class="mt-0.5 break-words text-xs text-slate-500">
        {{ item.organization_name?.trim() || 'Keine eindeutige Organisation' }}
      </p>
      <p v-if="item.subtitle" class="mt-1 break-words text-xs leading-5 text-slate-600">
        {{ item.subtitle }}
      </p>
      <p v-if="item.address" class="mt-1 break-words text-xs text-slate-600">{{ item.address }}</p>
      <div
        class="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs [&_a]:mt-0 [&_a]:border-0 [&_a]:bg-transparent [&_a]:p-0 [&_a]:text-xs"
      >
        <NuxtLink
          v-if="item.action"
          :to="item.action.href"
          :aria-label="`Im Admin ansehen: ${name}`"
          class="rounded text-fuchsia-700 underline-offset-4 hover:underline"
          >Im Admin ansehen</NuxtLink
        >
        <a
          v-if="item.public_url"
          :href="item.public_url"
          target="_blank"
          rel="noopener noreferrer"
          referrerpolicy="no-referrer"
          :aria-label="`${name} auf kulturbytes.de öffnen (neuer Tab)`"
          class="inline-flex items-center gap-1 rounded text-fuchsia-700 underline-offset-4 hover:underline"
          >Auf kulturbytes.de öffnen<AppIcon name="external" :size="13"
        /></a>
        <RecordMarkLink
          :entity-type="item.entity_type"
          :entity-key="item.entity_key"
          :aria-label="`Markierungen & Notizen zu ${name}`"
        />
      </div>
    </div>
    <div
      class="col-start-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500 md:contents"
    >
      <span
        v-if="status"
        class="inline-flex max-w-full break-words rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 md:col-start-3 md:row-start-1 md:max-w-40 md:self-start md:justify-self-end"
        >{{ status }}</span
      >
      <time
        v-if="item.created_at"
        class="tabular-nums md:col-start-4 md:row-start-1 md:justify-self-end"
        :datetime="item.created_at"
        :title="`${dateTime(item.created_at)} (${adminTimeZone})`"
        :aria-label="`Erstellt am ${dateTime(item.created_at)} (${adminTimeZone})`"
        >{{ activityTime(item.created_at, observedAt) }}</time
      >
      <span v-else class="md:col-start-4 md:row-start-1 md:justify-self-end">Ohne Zeitstempel</span>
    </div>
  </li>
</template>
