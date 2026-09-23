<script setup lang="ts">
import { computed } from 'vue'
import type { EntityDetail, EntitySection } from '#shared/contracts'
import { activityName, activityStatus } from '~/utils/activity'
import { graphHref } from '~/utils/graph'
const props = withDefaults(
  defineProps<{ item: EntityDetail['item']; section: EntitySection; organizationLabel?: string }>(),
  { organizationLabel: 'Organisation' },
)
const name = computed(() => activityName(props.item))
const status = computed(() => activityStatus(props.item.status))
const relationships = computed(() => graphHref(props.item.entity_type, props.item.entity_key))
</script>

<template>
  <div class="space-y-4 border-b border-slate-200 pb-5" data-entity-hero>
    <PageHeader :title="name" record>
      <template #leading><ActivityThumbnail :item="item" /></template>
      <template #badge>
        <EntityTypeBadge :type="item.entity_type" />
        <StatusBadge v-if="status" :label="status" />
      </template>
      <template #context>
        <p v-if="item.organization_name" class="type-body mt-2 break-words">
          {{ organizationLabel }}: {{ item.organization_name }}
        </p>
        <p v-if="item.subtitle" class="type-body mt-1 break-words">{{ item.subtitle }}</p>
      </template>
      <NuxtLink :to="`/${section}`" class="action-link">Zur Liste</NuxtLink>
    </PageHeader>
    <InlineAlert v-if="item.notice" tone="warning">{{ item.notice }}</InlineAlert>
    <div
      class="flex flex-wrap items-center gap-x-4 gap-y-2"
      role="group"
      aria-label="Datensatzaktionen"
    >
      <a
        v-if="item.public_url"
        :href="item.public_url"
        class="button-primary"
        target="_blank"
        rel="noopener noreferrer"
        referrerpolicy="no-referrer"
        :aria-label="`${name} auf kulturbytes.de öffnen (neuer Tab)`"
        >Auf kulturbytes.de öffnen <AppIcon name="external" :size="16"
      /></a>
      <NuxtLink v-if="relationships" :to="relationships" class="button">
        <AppIcon name="graph" :size="16" />Beziehungen
      </NuxtLink>
      <NuxtLink
        :to="{
          path: '/marks',
          query: { entity_type: item.entity_type, entity_key: item.entity_key, status: 'all' },
        }"
        class="action-link"
        :aria-label="`Markierungen & Notizen zu ${name}`"
        >Markierungen &amp; Notizen</NuxtLink
      >
    </div>
  </div>
</template>
