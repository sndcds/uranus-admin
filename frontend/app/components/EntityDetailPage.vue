<script setup lang="ts">
import DetailFacts from '~/components/DetailFacts.vue'
import SectionHeader from '~/components/SectionHeader.vue'
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import type { EntitySection, EntityDetail } from '#shared/contracts'
import { asFailure, type ApiFailure } from '#shared/errors'
import { entitySections, entityFactLabel } from '~/utils/entities'
const props = defineProps<{ section: EntitySection }>()
const route = useRoute()
const { $adminApi } = useNuxtApp()
const data = ref<EntityDetail | null>(null),
  error = ref<ApiFailure | null>(null)
const loading = ref(false)
let generation = 0
async function load() {
  const id = ++generation
  loading.value = true
  data.value = null
  error.value = null
  try {
    const result = await $adminApi.entity(
      props.section,
      String(route.params.id),
      Number(route.query.related_page ?? 1),
    )
    if (id === generation) data.value = result
  } catch (cause) {
    if (id === generation) error.value = asFailure(cause)
  } finally {
    if (id === generation) loading.value = false
  }
}
onMounted(load)
watch(() => route.fullPath, load)
watch(
  useState('admin-access-revision', () => 0),
  load,
)
onBeforeUnmount(() => {
  generation++
})
</script>
<template>
  <div class="space-y-5">
    <PageHeader
      :title="data?.item.entity_name ?? entitySections[section].title"
      description="Datensatz und verknüpfte Inhalte."
    >
    <RequestState :loading="loading" :error="error" :has-data="!!data" @retry="load" />
    <template v-if="data">
      <DataListShell as="ul"
        ><ActivityRow :item="data.item" :observed-at="data.observed_at"
      /></DataListShell>
      <dl class="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:grid-cols-2">
        <div>
          <dt class="text-xs text-slate-500">UUID</dt>
          <dd class="break-all text-sm">{{ data.item.entity_key }}</dd>
        </div>
        <template v-for="(value, field) in data.item.facts" :key="field"
          ><div v-if="value !== null">
            <dt class="text-xs text-slate-500">{{ entityFactLabel(section, field) }}</dt>
            <dd class="whitespace-pre-wrap break-words text-sm">
              {{ typeof value === 'boolean' ? (value ? 'Ja' : 'Nein') : value }}
            </dd>
          </div></template
        >
      </dl>
      <NuxtLink
        v-if="data"
        :to="{
          path: '/findings',
          query: {
            mode: 'persisted',
            entity_type: data.item.entity_type,
            entity_key: data.item.entity_key,
          },
        }"
        class="button"
        >Befunde zu diesem Datensatz</NuxtLink
      >
    </PageHeader>
    <RequestState :loading="loading" :error="error" :has-data="!!data" @retry="load" />
    <template v-if="data">
      <DataListShell as="ul"
        ><ActivityRow :item="data.item" :observed-at="data.observed_at"
      /></DataListShell>
      <DetailFacts
        :items="[
          { label: 'UUID', value: data.item.entity_key },
          ...Object.entries(data.item.facts).map(([field, value]) => ({
            label: factLabels[field as keyof typeof factLabels],
            value,
          })),
        ]"
      />
      <SectionHeader title="Verknüpfte Datensätze" />
      <p v-if="section === 'users' || section === 'organizations'" class="text-xs text-slate-500">
        Einladungen verwenden invited_at; der Mitgliedsstatus folgt has_joined. Ein
        Beitrittszeitpunkt ist nicht belegt.
      </p>
      <ResultSummary
        :total="data.related.pagination.total"
        :visible="data.related.items.length"
        noun="Verknüpfte Datensätze"
      />
      <DataListShell v-if="data.related.items.length" as="ul"
        ><ActivityRow
          v-for="item in data.related.items"
          :key="`${item.entity_type}:${item.entity_key}`"
          :item="item"
          :observed-at="data.observed_at"
      /></DataListShell>
      <EmptyState v-else message="Keine belegten Verknüpfungen vorhanden." />
      <PaginationBar
        :pagination="data.related.pagination"
        :to="(page) => ({ query: { related_page: String(page) } })"
      />
    </template>
  </div>
</template>
