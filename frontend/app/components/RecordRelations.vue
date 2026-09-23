<script setup lang="ts">
import type { EntityDetail } from '#shared/contracts'
defineProps<{ data: EntityDetail; loading: boolean }>()
const route = useRoute()
// Preserve the one bounded server page and its order; never infer complete domain groups.
</script>

<template>
  <RecordSection title="Verknüpfte Datensätze" :aria-busy="loading" data-record-relations>
    <p class="type-metadata">
      {{ data.related.items.length }} auf dieser Seite von
      {{ data.related.pagination.total }} insgesamt.
      <slot name="description">Gemeinsame Liste nach Objektart und Name.</slot>
      <span v-if="data.related.pagination.pages > 1">
        Weitere verknüpfte Datensätze stehen auf anderen Seiten.
      </span>
    </p>
    <DataListShell v-if="data.related.items.length" as="ul" aria-label="Verknüpfte Datensätze">
      <ActivityRow
        v-for="item in data.related.items"
        :key="`${item.entity_type}:${item.entity_key}`"
        :item="item"
        :observed-at="data.observed_at"
        grouped
      />
    </DataListShell>
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
  </RecordSection>
</template>
