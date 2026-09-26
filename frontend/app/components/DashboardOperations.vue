<script setup lang="ts">
import { onMounted, watch } from 'vue'
import type { ActivityPage, GeocodePage, InboxPage, Period } from '#shared/contracts'
import { inboxFiltersSchema } from '#shared/contracts'
import { useOperationsRequest } from '~/composables/useOperationsRequest'
import { geocodeStatuses } from '~/utils/geocoding'
import { metric } from '~/utils/presentation'
const props = defineProps<{ period: Period; geoScopeId?: string }>()
const { $adminApi } = useNuxtApp()
const inbox = useOperationsRequest<InboxPage>()
const geocoding = useOperationsRequest<GeocodePage>()
const activity = useOperationsRequest<ActivityPage>()
function loadInbox() {
  return inbox.load('global', () => $adminApi.inbox(inboxFiltersSchema.parse({ page_size: 1 })))
}
function loadGeocoding() {
  return geocoding.load('global', () => $adminApi.geocodeRequests({ page_size: 1 }))
}
function loadActivity() {
  return activity.load(`${props.period}:${props.geoScopeId ?? ''}`, () =>
    $adminApi.activity({ period: props.period, geo_scope_id: props.geoScopeId, page_size: 4 }),
  )
}
function refresh() {
  return Promise.all([loadInbox(), loadGeocoding(), loadActivity()])
}
onMounted(refresh)
watch(() => [props.period, props.geoScopeId], loadActivity)
defineExpose({ refresh })
</script>
<template>
  <div class="space-y-4">
    <div class="grid items-start gap-4 lg:grid-cols-2">
      <RecordSection
        title="Inbox"
        description="Systemweiter Arbeitsbestand · unabhängig vom Zeitraum"
        surface="panel"
      >
        <template #actions
          ><NuxtLink to="/inbox" class="action-link">Inbox öffnen</NuxtLink></template
        >
        <RequestState
          :loading="inbox.loading.value"
          :error="inbox.error.value"
          :has-data="!!inbox.data.value"
          @retry="loadInbox"
        />
        <template v-if="inbox.data.value">
          <CompactFacts
            :items="[
              { label: 'Sichtbare Aufgaben', value: inbox.data.value.pagination.total },
              { label: 'Kritisch', value: inbox.data.value.counts.critical },
              { label: 'Überfällig', value: inbox.data.value.counts.overdue },
            ]"
          />
          <div class="flex flex-wrap gap-x-4">
            <NuxtLink to="/inbox?attention=critical" class="action-link"
              >Kritische Aufgaben prüfen</NuxtLink
            >
            <NuxtLink to="/inbox?attention=overdue" class="action-link"
              >Überfällige Aufgaben</NuxtLink
            >
          </div>
          <EmptyState
            v-if="!inbox.data.value.pagination.total"
            compact
            message="Keine sichtbaren Aufgaben in der Inbox."
          />
        </template>
      </RecordSection>
      <RecordSection
        title="Geocoding"
        description="Systemweiter, zuletzt gespeicherter Prüfstand"
        surface="panel"
      >
        <template #actions
          ><NuxtLink to="/geocoding" class="action-link"
            >Standortvorschläge öffnen</NuxtLink
          ></template
        >
        <RequestState
          :loading="geocoding.loading.value"
          :error="geocoding.error.value"
          :has-data="!!geocoding.data.value"
          @retry="loadGeocoding"
        />
        <ul v-if="geocoding.data.value" class="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <li
            v-for="status in ['failed', 'pending', 'checking', 'candidate', 'ambiguous'] as const"
            :key="status"
          >
            <NuxtLink :to="`/geocoding?status=${status}`" class="action-link text-sm">
              {{ geocodeStatuses[status] }}: {{ metric(geocoding.data.value.counts[status] ?? 0) }}
            </NuxtLink>
          </li>
        </ul>
        <EmptyState
          v-if="geocoding.data.value?.pagination.total === 0"
          compact
          message="Noch keine Standortprüfungen vorhanden."
        />
      </RecordSection>
    </div>
    <RecordSection
      title="Letzte Aktivitäten"
      description="Neuanlagen im gewählten Zeitraum; belegte Änderungen stehen im Datensatzverlauf."
      surface="table"
    >
      <template #actions
        ><NuxtLink
          :to="{ path: '/activity', query: { period, geo_scope_id: geoScopeId } }"
          class="action-link"
          >Aktivität öffnen</NuxtLink
        ></template
      >
      <div v-if="activity.loading.value || activity.error.value" class="p-3">
        <RequestState
          :loading="activity.loading.value"
          :error="activity.error.value"
          :has-data="!!activity.data.value"
          @retry="loadActivity"
        />
      </div>
      <DataListShell v-if="activity.data.value?.items.length" as="ul" dense>
        <ActivityRow
          v-for="item in activity.data.value.items"
          :key="`${item.entity_type}:${item.entity_key}`"
          :item="item"
          :observed-at="activity.data.value.observed_at"
          grouped
          dense
        />
      </DataListShell>
      <EmptyState
        v-else-if="activity.data.value && !activity.loading.value"
        compact
        message="Keine Neuanlagen im gewählten Zeitraum."
      />
    </RecordSection>
    <RecordSection title="Social Publishing" surface="subtle">
      <p class="type-body">
        Nicht verfügbar: Veröffentlichungs- und Scheduling-Daten werden von der Admin-API noch nicht
        geliefert.
      </p>
      <NuxtLink to="/social-publishing" class="action-link">Verfügbarkeit ansehen</NuxtLink>
    </RecordSection>
  </div>
</template>
