<script setup lang="ts">
import type { ResearchQuery } from '#shared/contracts'
import { researchStatuses } from '~/utils/research'
const props = defineProps<{
  query: ResearchQuery
  categories: { id: number; name: string }[]
  types?: boolean
  compact?: boolean
}>()
const emit = defineEmits<{ apply: [query: ResearchQuery] }>()
const draft = ref<ResearchQuery>({ entity_type: 'all', ...props.query })
watch(
  () => props.query,
  (q) => {
    draft.value = { entity_type: 'all', ...q }
  },
  { deep: true },
)
const error = ref('')
const id = useId()
const extra = useTemplateRef('extra')
function apply() {
  error.value = ''
  if (draft.value.from_date && draft.value.to_date && draft.value.from_date > draft.value.to_date) {
    error.value = 'Das Ende muss am oder nach dem Beginn liegen.'
    return
  }
  const next = { ...draft.value, page: undefined }
  extra.value?.close()
  emit('apply', next)
}
function closeExtra() {
  draft.value = { entity_type: 'all', ...props.query }
  error.value = ''
}
function primaryChange() {
  if (props.compact) apply()
}
</script>
<template>
  <FilterBar
    class="research-filters"
    :class="{ 'research-filters-compact': compact }"
    compact
    stack-actions
    @apply="apply"
  >
    <fieldset class="research-period min-w-0">
      <legend class="sr-only">Zeitraum</legend>
      <span class="label" aria-hidden="true">Zeitraum</span>
      <div class="mt-1 flex items-center rounded-lg border border-slate-200 bg-white">
        <label class="min-w-0 flex-1"
          ><span class="sr-only">Von</span
          ><input
            v-model="draft.from_date"
            class="input border-0 px-2"
            type="date"
            @change="primaryChange"
        /></label>
        <span class="text-slate-400" aria-hidden="true">→</span>
        <label class="min-w-0 flex-1"
          ><span class="sr-only">Bis</span
          ><input
            v-model="draft.to_date"
            class="input border-0 px-2"
            type="date"
            @change="primaryChange"
        /></label>
      </div>
    </fieldset>
    <label class="label relative"
      >Stadt<AppIcon name="pin" :size="17" class="research-filter-icon" /><input
        v-model="draft.city"
        class="input mt-1 pl-9"
        maxlength="100"
        placeholder="Alle Städte"
        @change="primaryChange"
    /></label>
    <label class="label relative"
      >Kategorie<AppIcon name="tag" :size="17" class="research-filter-icon" /><select
        v-model="draft.category"
        aria-label="Kategorie"
        class="input mt-1 pl-9"
        @change="primaryChange"
      >
        <option :value="undefined">Alle Kategorien</option>
        <option v-for="category in categories" :key="category.id" :value="category.id">
          {{ category.name }}
        </option>
      </select></label
    >
    <label class="label relative"
      >Status<AppIcon name="settings" :size="17" class="research-filter-icon" /><select
        v-model="draft.status"
        aria-label="Status"
        class="input mt-1 pl-9"
        @change="primaryChange"
      >
        <option :value="undefined">Alle öffentlichen Status</option>
        <option v-for="(label, value) in researchStatuses" :key="value" :value="value">
          {{ label }}
        </option>
      </select></label
    >
    <template v-if="!compact">
      <ResearchEntitySelect
        v-model="draft.organization_id"
        kind="organization"
        label="Organisation"
      />
      <ResearchEntitySelect v-model="draft.venue_id" kind="venue" label="Ort" />
      <label v-if="types" :for="id" class="label"
        >Datensatztyp<select
          :id="id"
          v-model="draft.entity_type"
          aria-label="Datensatztyp"
          class="input mt-1"
        >
          <option value="all">Alle</option>
          <option value="event">Veranstaltungen</option>
          <option value="venue">Orte</option>
          <option value="organization">Organisationen</option>
        </select></label
      >
    </template>
    <template #actions>
      <button v-if="compact" class="button whitespace-nowrap" type="button" @click="extra?.open()">
        <AppIcon name="filter" />Weitere Filter
      </button>
      <button v-else class="button" type="submit">Filter anwenden</button>
    </template>
    <template #help
      ><p v-if="error" role="alert" class="mt-2 text-sm text-rose-700">{{ error }}</p></template
    >
  </FilterBar>
  <AppModal v-if="compact" ref="extra" title="Weitere Filter" @close="closeExtra">
    <form class="mt-5 space-y-4" @submit.prevent="apply">
      <ResearchEntitySelect
        v-model="draft.organization_id"
        kind="organization"
        label="Organisation"
      />
      <ResearchEntitySelect v-model="draft.venue_id" kind="venue" label="Ort" />
      <label v-if="types" class="label"
        >Datensatztyp<select
          v-model="draft.entity_type"
          aria-label="Datensatztyp"
          class="input mt-1"
        >
          <option value="all">Alle</option>
          <option value="event">Veranstaltungen</option>
          <option value="venue">Orte</option>
          <option value="organization">Organisationen</option>
        </select></label
      >
      <p class="type-metadata">
        Der Zeitraum bezieht sich auf den Beginn eines Termins und schließt beide Tage ein.
      </p>
      <p v-if="error" role="alert" class="text-sm text-rose-700">{{ error }}</p>
      <button class="button" type="submit">Filter anwenden</button>
    </form>
  </AppModal>
</template>
<style scoped>
@reference '../assets/css/main.css';
.research-filters {
  @apply rounded-none border-0 p-0;
}
.research-filter-icon {
  @apply pointer-events-none absolute bottom-3.5 left-3 text-slate-600;
}
.research-filters-compact .research-filter-icon {
  @apply bottom-5 left-6;
}
.research-filters :deep(.label) {
  @apply mb-0 font-normal;
}
.research-filters-compact :deep(> div) {
  grid-template-columns: minmax(17rem, 1.6fr) repeat(3, minmax(0, 1fr)) auto;
  @apply gap-2;
}
.research-filters-compact :deep(> div > div:last-child) {
  @apply col-span-1 self-end;
}
.research-filters-compact :deep(> div > .label),
.research-filters-compact .research-period {
  @apply rounded-lg border border-slate-200 px-3 py-2;
}
@media (max-width: 1279px) {
  .research-filters-compact :deep(> div) {
    grid-template-columns: minmax(17rem, 2fr) minmax(0, 1fr) minmax(0, 1fr);
  }
}
</style>
