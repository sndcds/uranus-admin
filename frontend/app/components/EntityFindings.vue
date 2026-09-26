<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { filtersSchema, type FindingPage } from '#shared/contracts'
import { useOperationsRequest } from '~/composables/useOperationsRequest'
const props = defineProps<{ entityType: string; entityKey: string }>()
const { $adminApi } = useNuxtApp()
const { data, loading, error, load: request } = useOperationsRequest<FindingPage>()
function load() {
  return request(`${props.entityType}:${props.entityKey}`, () =>
    $adminApi.findings(
      filtersSchema.parse({
        entity_type: props.entityType,
        entity_key: props.entityKey,
        active_only: true,
        page_size: 5,
      }),
    ),
  )
}
onMounted(load)
watch(() => [props.entityType, props.entityKey], load)
</script>
<template>
  <RecordSection
    title="Aktive Befunde"
    surface="table"
    description="Bis zu fünf priorisierte Befunde zu diesem Datensatz."
  >
    <template #actions
      ><NuxtLink
        :to="{
          path: '/findings',
          query: {
            mode: 'persisted',
            entity_type: entityType,
            entity_key: entityKey,
            active_only: 'true',
          },
        }"
        class="action-link"
        >Alle aktiven Befunde</NuxtLink
      ></template
    >
    <div v-if="loading || error" class="p-3">
      <RequestState :loading="loading" :error="error" :has-data="!!data" @retry="load" />
    </div>
    <FindingsList v-if="data?.items.length" :items="data.items" compact @refresh="load" />
    <EmptyState
      v-else-if="data && !loading"
      compact
      message="Keine aktiven Befunde zu diesem Datensatz."
    />
  </RecordSection>
</template>
