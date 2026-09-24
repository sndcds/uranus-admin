<script setup lang="ts">
import { computed } from 'vue'
import type { EntitySection } from '#shared/contracts'
import { activityName, activityStatus, activityMapUrl } from '~/utils/activity'
import {
  collectionContext,
  entityCollectionFacts,
  type CollectionRecord,
} from '~/utils/collections'
import { operationValue } from '~/utils/operations'
const props = defineProps<{ section: EntitySection; item: CollectionRecord }>()
const name = computed(() => activityName(props.item))
const context = computed(() => collectionContext(props.section, props.item))
const facts = computed(() => entityCollectionFacts(props.section, props.item))
const status = computed(() => activityStatus(props.item.status))
const mapUrl = computed(() => activityMapUrl(props.item.location))
const subtitle = computed(() =>
  props.item.subtitle?.trim() !== props.item.entity_name.trim() &&
  !context.value.includes(props.item.subtitle?.trim() ?? '')
    ? props.item.subtitle
    : null,
)
</script>

<template>
  <li class="collection-row data-row" data-collection-row>
    <div class="flex min-w-0 items-start gap-3">
      <ActivityThumbnail :item="item" dense />
      <div class="min-w-0 space-y-1">
        <h3 class="text-sm font-semibold text-slate-900 [overflow-wrap:anywhere]">{{ name }}</h3>
        <p v-if="subtitle" class="text-xs text-slate-600 [overflow-wrap:anywhere]">
          {{ subtitle }}
        </p>
        <EntityTypeBadge :type="item.entity_type" />
      </div>
    </div>
    <div class="min-w-0 text-xs text-slate-600 [overflow-wrap:anywhere]">
      <p v-for="line in context" :key="line" class="mb-1">{{ line }}</p>
      <a
        v-if="mapUrl"
        :href="mapUrl"
        class="action-link"
        target="_blank"
        rel="noopener noreferrer"
        referrerpolicy="no-referrer"
        :aria-label="`${name} auf OpenStreetMap öffnen (neuer Tab)`"
        >OpenStreetMap<AppIcon name="external" :size="13"
      /></a>
      <span v-if="!context.length && !mapUrl" class="operations-meta">Kein weiterer Kontext</span>
    </div>
    <dl v-if="section !== 'spaces'" class="min-w-0 space-y-1 text-xs [overflow-wrap:anywhere]">
      <div v-for="fact in facts" :key="fact.label" class="flex flex-wrap items-baseline gap-x-1">
        <dt class="operations-meta">{{ fact.label }}:</dt>
        <dd class="font-medium text-slate-800">{{ ' ' }}{{ operationValue(fact.value) }}</dd>
      </div>
    </dl>
    <div class="min-w-0 space-y-2 text-xs text-slate-600">
      <StatusBadge v-if="status" :label="status" />
      <div>
        <span class="operations-meta block">Erstellt</span
        ><OperationTime :value="item.created_at" />
      </div>
    </div>
    <div class="collection-actions flex min-w-0 flex-wrap items-start gap-x-3">
      <NuxtLink
        v-if="item.action"
        :to="item.action.href"
        class="button text-xs"
        :aria-label="`Öffnen: ${name}`"
        >Öffnen</NuxtLink
      >
      <a
        v-if="item.public_url"
        :href="item.public_url"
        class="action-link"
        target="_blank"
        rel="noopener noreferrer"
        referrerpolicy="no-referrer"
        :aria-label="`${name} auf kulturbytes.de öffnen (neuer Tab)`"
        >kulturbytes.de<AppIcon name="external" :size="13"
      /></a>
      <GraphLink
        :entity-type="item.entity_type"
        :entity-key="item.entity_key"
        class="action-link"
      />
      <RecordMarkLink
        :entity-type="item.entity_type"
        :entity-key="item.entity_key"
        variant="action"
        :aria-label="`Markierungen & Notizen zu ${name}`"
      />
    </div>
    <InlineAlert v-if="item.notice" tone="warning" role="status" class="collection-notice">{{
      item.notice
    }}</InlineAlert>
  </li>
</template>
