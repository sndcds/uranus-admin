<script setup lang="ts">
import GraphLink from './GraphLink.vue'
import VenueScopeBadge from './VenueScopeBadge.vue'
import { computed } from 'vue'
import type { EntityDetail, EntitySection } from '#shared/contracts'
import { activityName, activityStatus } from '~/utils/activity'
const props = withDefaults(
  defineProps<{
    item: EntityDetail['item']
    section: EntitySection
    organizationLabel?: string
    inspector?: boolean
  }>(),
  { organizationLabel: 'Organisation' },
)
const name = computed(() => activityName(props.item))
const status = computed(() => activityStatus(props.item.status))
</script>

<template>
  <div class="operations-panel space-y-3 p-operations-panel" data-entity-hero>
    <PageHeader :title="name" record>
      <template #leading
        ><slot name="leading"><ActivityThumbnail :item="item" dense /></slot
      ></template>
      <template #badge>
        <EntityTypeBadge :type="item.entity_type" />
        <VenueScopeBadge
          v-if="item.entity_type === 'venue' && item.venue_scope"
          :scope="item.venue_scope"
        />
        <StatusBadge v-if="status" :label="status" />
      </template>
      <template #context>
        <slot name="context">
          <p v-if="item.organization_name" class="type-body mt-2 break-words">
            {{ organizationLabel }}: {{ item.organization_name }}
          </p>
          <p v-if="item.subtitle" class="type-body mt-1 break-words">{{ item.subtitle }}</p>
        </slot>
      </template>
    </PageHeader>
    <InlineAlert v-if="item.notice" tone="warning">{{ item.notice }}</InlineAlert>
    <div class="flex flex-wrap items-center gap-2" role="group" aria-label="Datensatzaktionen">
      <a
        v-if="item.public_url"
        :href="item.public_url"
        class="button-primary button-compact"
        target="_blank"
        rel="noopener noreferrer"
        referrerpolicy="no-referrer"
        :aria-label="`${name} auf kulturbytes.de öffnen (neuer Tab)`"
        >Auf kulturbytes.de öffnen <AppIcon name="external" :size="16"
      /></a>
      <GraphLink :entity-type="item.entity_type" :entity-key="item.entity_key" variant="compact" />
      <EntityInspectorLink
        v-if="!inspector"
        :entity-type="item.entity_type"
        :entity-key="item.entity_key"
      />
      <NuxtLink
        :to="{
          path: '/marks',
          query: { entity_type: item.entity_type, entity_key: item.entity_key, status: 'all' },
        }"
        class="button button-compact"
        :aria-label="`Markierungen & Notizen zu ${name}`"
        >Markierungen &amp; Notizen</NuxtLink
      >
      <NuxtLink :to="`/${section}`" class="button button-compact sm:ml-auto">Zur Liste</NuxtLink>
    </div>
  </div>
</template>
