<script setup lang="ts">
import VenueScopeBadge from './VenueScopeBadge.vue'
import { computed } from 'vue'
import GraphLink from './GraphLink.vue'
import type { ActivityItem } from '~/utils/activity'
import { activityName, activityStatus, activityMapUrl } from '~/utils/activity'
import { activityTime, clockTime, dateTime, adminTimeZone } from '~/utils/presentation'
const props = defineProps<{
  item: ActivityItem
  observedAt: string
  grouped?: boolean
  dense?: boolean
  relation?: boolean
}>()
const name = computed(() => activityName(props.item))
const mapUrl = computed(() => activityMapUrl(props.item.location))
const status = computed(() => activityStatus(props.item.status))
</script>

<template>
  <li
    class="grid min-w-0 gap-x-3 gap-y-2 data-row transition-colors"
    :class="
      dense
        ? 'activity-row-dense'
        : 'grid-cols-[6rem_minmax(0,1fr)] md:grid-cols-[8rem_minmax(0,1fr)_auto_7rem]'
    "
  >
    <ActivityThumbnail :item="item" :dense="dense" />
    <div class="min-w-0">
      <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
        <component
          :is="grouped ? 'h4' : 'h3'"
          class="min-w-0 break-words text-sm font-semibold text-slate-900 [overflow-wrap:anywhere]"
          :title="item.entity_name"
        >
          {{ name }}
        </component>
        <EntityTypeBadge :type="item.entity_type" />
        <VenueScopeBadge
          v-if="item.entity_type === 'venue' && item.venue_scope"
          :scope="item.venue_scope"
        />
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
      <InlineAlert
        v-if="item.notice"
        tone="warning"
        role="status"
        class="mt-2 flex items-start gap-2"
      >
        <AppIcon name="warning" :size="18" />
        <span class="min-w-0 break-words">{{ item.notice }}</span>
      </InlineAlert>
      <p v-if="item.address" class="mt-1 break-words text-xs text-slate-600">{{ item.address }}</p>
      <p v-if="mapUrl && item.location" class="mt-1 text-xs text-slate-500">
        <a
          :href="mapUrl"
          target="_blank"
          rel="noopener noreferrer"
          referrerpolicy="no-referrer"
          :aria-label="`${name} auf OpenStreetMap öffnen (neuer Tab)`"
          class="inline-flex min-h-11 flex-wrap items-center gap-1 rounded text-fuchsia-700 hover:underline"
        >
          <AppIcon name="pin" :size="13" />
          <span v-if="!dense">{{ item.location.latitude }}, {{ item.location.longitude }} · </span
          >OpenStreetMap
          <AppIcon name="external" :size="13" />
        </a>
      </p>
      <slot name="context" />
      <div class="mt-2 flex flex-wrap items-center gap-2 text-xs">
        <NuxtLink
          v-if="item.action"
          :to="item.action.href"
          :aria-label="`Öffnen: ${name}`"
          class="button button-compact"
          >Öffnen</NuxtLink
        >
        <a
          v-if="item.public_url"
          :href="item.public_url"
          target="_blank"
          rel="noopener noreferrer"
          referrerpolicy="no-referrer"
          :aria-label="`${name} auf kulturbytes.de öffnen (neuer Tab)`"
          class="action-link text-xs"
          >Auf kulturbytes.de öffnen<AppIcon name="external" :size="13"
        /></a>
        <EntityInspectorLink :entity-type="item.entity_type" :entity-key="item.entity_key" />
        <GraphLink
          :entity-type="item.entity_type"
          :entity-key="item.entity_key"
          :variant="relation ? 'compact' : 'action'"
        />
        <RecordMarkLink
          :variant="relation ? 'compact' : 'action'"
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
        >{{
          relation
            ? dateTime(item.created_at)
            : dense && grouped
              ? clockTime(item.created_at)
              : activityTime(item.created_at, observedAt)
        }}</time
      >
      <span v-else class="md:col-start-4 md:row-start-1 md:justify-self-end">Ohne Zeitstempel</span>
    </div>
  </li>
</template>
