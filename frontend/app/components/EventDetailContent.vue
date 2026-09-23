<script setup lang="ts">
import { computed } from 'vue'
import type { EntityDetail } from '#shared/contracts'
const props = defineProps<{ data: EntityDetail; loading: boolean }>()
const route = useRoute()
// The page is a bounded snapshot. Group by the supplied type; never infer edge roles or dates.
const relationGroups = computed(() =>
  [
    { title: 'Termine', types: ['event_date'] },
    { title: 'Veranstalter', types: ['organization'] },
    { title: 'Orte & Räume', types: ['venue', 'space'] },
    { title: 'Medien', types: ['image'] },
    {
      title: 'Weitere Beziehungen',
      types: ['user', 'team_membership', 'partner_request', 'event'],
    },
  ]
    .map((group) => ({
      ...group,
      items: props.data.related.items.filter((item) => group.types.includes(item.entity_type)),
    }))
    .filter((group) => group.items.length),
)
const facts = computed(() =>
  [
    { label: 'Termine insgesamt', value: props.data.item.facts.event_dates },
    { label: 'Standardort', value: props.data.item.facts.venue_name },
    { label: 'Standardraum', value: props.data.item.facts.space_name },
  ].filter((fact) => fact.value !== null && fact.value !== ''),
)
const findingsHref = computed(() => ({
  path: '/findings',
  query: {
    mode: 'persisted',
    entity_type: props.data.item.entity_type,
    entity_key: props.data.item.entity_key,
  },
}))
</script>

<template>
  <RecordSection v-if="facts.length" title="Auf einen Blick">
    <dl class="grid gap-4 sm:grid-cols-3">
      <div v-for="fact in facts" :key="fact.label" class="min-w-0">
        <dt class="type-metadata">{{ fact.label }}</dt>
        <dd class="type-body mt-1 break-words font-semibold">{{ fact.value }}</dd>
      </div>
    </dl>
  </RecordSection>
  <RecordSection v-if="data.item.facts.description?.trim()" title="Beschreibung">
    <MarkdownContent :source="data.item.facts.description" />
  </RecordSection>
  <div class="space-y-4 sm:space-y-6" :aria-busy="loading" data-event-relations>
    <p class="type-metadata">
      Verknüpfte Datensätze: {{ data.related.items.length }} auf dieser Seite von
      {{ data.related.pagination.total }} insgesamt.
      <span v-if="data.related.pagination.pages > 1"
        >Die Gruppen zeigen nur die aktuelle Seite.</span
      >
    </p>
    <RecordSection v-for="group in relationGroups" :key="group.title" :title="group.title">
      <DataListShell as="ul" :aria-label="group.title">
        <ActivityRow
          v-for="item in group.items"
          :key="`${item.entity_type}:${item.entity_key}`"
          :item="item"
          :observed-at="data.observed_at"
          grouped
        />
      </DataListShell>
    </RecordSection>
    <EmptyState
      v-if="!data.related.items.length"
      message="Keine belegten Verknüpfungen auf dieser Seite vorhanden."
    />
    <PaginationBar
      v-if="data.related.pagination.pages > 1"
      :pagination="data.related.pagination"
      :loading="loading"
      label="Verknüpfte Datensätze – Seitennavigation"
      :to="(page) => ({ query: { ...route.query, related_page: String(page) } })"
    />
  </div>
  <RecordSection title="Qualität & Arbeitsstand">
    <dl class="flex flex-wrap gap-x-10 gap-y-3">
      <div v-if="data.item.finding_count !== null">
        <dt class="type-metadata">Gespeicherte Befunde ohne behobene</dt>
        <dd class="type-body mt-1 font-semibold">{{ data.item.finding_count }}</dd>
      </div>
      <div v-if="data.item.mark_count !== null">
        <dt class="type-metadata">Markierungen einschließlich erledigter</dt>
        <dd class="type-body mt-1 font-semibold">{{ data.item.mark_count }}</dd>
      </div>
    </dl>
    <p v-if="data.item.finding_count === null && data.item.mark_count === null" class="type-body">
      Der Arbeitsstand ist nicht verfügbar.
    </p>
    <NuxtLink :to="findingsHref" class="action-link">Befunde anzeigen</NuxtLink>
  </RecordSection>
</template>
