<script setup lang="ts">
import { computed } from 'vue'
import GraphLink from './GraphLink.vue'
import type { ActivityItem } from '~/utils/activity'
import { activityName, activityStatus, activityMapUrl } from '~/utils/activity'
import { activityTime, dateTime, adminTimeZone } from '~/utils/presentation'
const props = defineProps<{ item: ActivityItem; observedAt: string; grouped?: boolean }>()
const name = computed(() => activityName(props.item))
const mapUrl = computed(() => activityMapUrl(props.item.location))
const status = computed(() => activityStatus(props.item.status))
</script>

<template>
  <li
    class="grid min-w-0 grid-cols-[6rem_minmax(0,1fr)] gap-x-3 gap-y-2 data-row transition-colors md:grid-cols-[8rem_minmax(0,1fr)_auto_7rem]"
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
        <EntityTypeBadge :type="item.entity_type" />
      </div>
      <p class="mt-0.5 break-words text-xs text-slate-500">
        {{ item.organization_name?.trim() || 'Keine eindeutige Organisation' }}
      </p>
      <p
        v-if="item.entity_type === 'user' && item.email"
        class="mt-1 break-words text-xs text-slate-600"
      >
        <span class="font-medium">E-Mail:</span> {{ item.email }}
      </p>
      <p v-if="item.subtitle" class="mt-1 break-words text-xs leading-5 text-slate-600">
        {{ item.subtitle }}
      </p>
      <p v-if="item.address" class="mt-1 break-words text-xs text-slate-600">{{ item.address }}</p>
      <p v-if="mapUrl && item.location" class="mt-1 text-xs text-slate-500">
        <a
          :href="mapUrl"
          target="_blank"
          rel="noopener noreferrer"
          referrerpolicy="no-referrer"
          :aria-label="`${name} auf OpenStreetMap öffnen (neuer Tab)`"
          class="inline-flex flex-wrap items-center gap-1 rounded text-fuchsia-700 hover:underline"
        >
          <AppIcon name="pin" :size="13" />
          {{ item.location.latitude }}, {{ item.location.longitude }} · OpenStreetMap
          <AppIcon name="external" :size="13" />
        </a>
      </p>
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
        <GraphLink :entity-type="item.entity_type" :entity-key="item.entity_key" />
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
      <StatusBadge
        v-if="status"
        :label="status"
        class="md:col-start-3 md:row-start-1 md:max-w-40 md:self-start md:justify-self-end"
      />
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
