<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { ResearchArea } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import AppModal from './AppModal.vue'
import AdministrativeAreaSelect from './AdministrativeAreaSelect.vue'
import { geoAreaLabel, supportsGeoScope, geoPagination, isSpatialType } from '~/utils/geo'
import { researchAreaLabel } from '~/utils/research'
import { useFilterPreferencesStore } from '~/stores/filter-preferences'

const preferences = useFilterPreferencesStore()
const props = withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const modal = ref<InstanceType<typeof AppModal> | null>(null)
const selector = ref<InstanceType<typeof AdministrativeAreaSelect> | null>(null)
const interactive = ref(false)
const error = ref('')
const selected = computed(() => preferences.sharedGeoScope)
const label = computed(() =>
  selected.value
    ? 'area_type' in selected.value
      ? researchAreaLabel(selected.value)
      : geoAreaLabel(selected.value)
    : 'Gebiet auswählen',
)
onMounted(() => {
  interactive.value = true
})
async function apply(area: ResearchArea) {
  if (!auth.isAdmin) return
  error.value = ''
  preferences.setGeoScope(area)
  try {
    if (supportsGeoScope(route.path))
      await router.push({
        query: {
          ...route.query,
          geo_scope_id: area.id,
          ...(geoPagination(route.path) ? { page: '1', cursor: undefined } : {}),
          ...(['/activity', '/graph'].includes(route.path) &&
          typeof route.query.entity_type === 'string' &&
          !isSpatialType(route.query.entity_type)
            ? { entity_type: undefined }
            : {}),
        },
        hash: route.hash,
      })
    modal.value?.close()
  } catch (cause) {
    error.value = asFailure(cause).message
  }
}
async function clear() {
  preferences.setGeoScope(null)
  const next = { ...route.query }
  delete next.geo_scope_id
  if (geoPagination(route.path)) next.page = '1'
  delete next.cursor
  await router.push({ query: next, hash: route.hash })
}
</script>
<template>
  <div
    class="flex min-w-0 max-w-full items-center gap-2"
    :class="props.compact ? 'w-full flex-nowrap' : 'flex-wrap'"
  >
    <button
      type="button"
      class="button max-w-full min-w-0"
      :class="props.compact ? 'min-h-11 flex-1 justify-between px-3' : ''"
      :disabled="!interactive"
      :title="label"
      @click="modal?.open()"
    >
      <span :class="props.compact ? 'max-w-full truncate' : 'max-w-60 truncate'">
        Gebiet: {{ selected?.name ?? 'Alle' }}
      </span>
      <span class="sr-only"> – Gebiet auswählen</span>
    </button>
    <button
      v-if="selected"
      type="button"
      class="button"
      :class="props.compact ? 'min-h-11 w-11 shrink-0 px-0' : ''"
      aria-label="Gebiet zurücksetzen"
      :disabled="!interactive"
      @click="clear"
    >
      ×
    </button>
    <AppModal ref="modal" title="Gebiet auswählen" @close="selector?.reset()">
      <div class="mt-4 space-y-3">
        <AdministrativeAreaSelect
          ref="selector"
          workspace="operations"
          label="Administratives Gebiet suchen"
          @select="apply"
          @close="modal?.close()"
        />
        <p v-if="error" role="alert" class="text-sm text-red-700">{{ error }}</p>
        <OsmAttribution />
        <p class="text-xs text-slate-500">Importierte Gemeinden und Kommunen aus OpenStreetMap.</p>
      </div>
    </AppModal>
  </div>
</template>
