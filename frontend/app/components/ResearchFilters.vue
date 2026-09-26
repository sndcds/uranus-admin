<script setup lang="ts">
import type { ResearchQuery } from '#shared/contracts'
import { researchStatuses } from '~/utils/research'
const props = defineProps<{
  query: ResearchQuery
  categories: { id: number; name: string }[]
  types?: boolean
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
function apply() {
  error.value = ''
  if (draft.value.from_date && draft.value.to_date && draft.value.from_date > draft.value.to_date) {
    error.value = 'Das Ende muss am oder nach dem Beginn liegen.'
    return
  }
  emit('apply', { ...draft.value, page: undefined })
}
</script>
<template>
  <FilterBar compact stack-actions @apply="apply">
    <label class="label"
      >Von<input v-model="draft.from_date" class="input mt-1" type="date"
    /></label>
    <label class="label">Bis<input v-model="draft.to_date" class="input mt-1" type="date" /></label>
    <label class="label"
      >Stadt<input
        v-model="draft.city"
        class="input mt-1"
        maxlength="100"
        placeholder="z. B. Flensburg"
    /></label>
    <label class="label"
      >Kategorie<select v-model="draft.category" class="input mt-1">
        <option :value="undefined">Alle Kategorien</option>
        <option v-for="category in categories" :key="category.id" :value="category.id">
          {{ category.name }}
        </option>
      </select></label
    >
    <label class="label"
      >Status<select v-model="draft.status" class="input mt-1">
        <option :value="undefined">Alle öffentlichen Status</option>
        <option v-for="(label, value) in researchStatuses" :key="value" :value="value">
          {{ label }}
        </option>
      </select></label
    >
    <ResearchEntitySelect
      v-model="draft.organization_id"
      kind="organization"
      label="Organisation"
    />
    <ResearchEntitySelect v-model="draft.venue_id" kind="venue" label="Ort" />
    <label v-if="types" :for="id" class="label"
      >Datensatztyp<select :id="id" v-model="draft.entity_type" class="input mt-1">
        <option value="all">Alle</option>
        <option value="event">Veranstaltungen</option>
        <option value="venue">Orte</option>
        <option value="organization">Organisationen</option>
      </select></label
    >
    <template #actions
      ><button class="button-primary" type="submit">Filter anwenden</button></template
    >
    <template #help
      ><p class="type-metadata mt-2">
        Zeitraum: Beginn des Veranstaltungstermins, einschließlich beider Tage. Orts- und
        Organisationszahlen zählen unterschiedliche Veranstaltungen.
      </p>
      <p v-if="error" role="alert" class="text-sm text-rose-700">{{ error }}</p></template
    >
  </FilterBar>
</template>
