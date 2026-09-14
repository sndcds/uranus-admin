<script setup lang="ts">
import type { FindingFilters } from '#shared/contracts'
import { filtersSchema } from '#shared/contracts'
const props = defineProps<{ filters: FindingFilters }>()
const emit = defineEmits<{ apply: [filters: FindingFilters] }>()
const severity = ref(props.filters.severity ?? '')
const organization = ref(props.filters.organization_id ?? '')
const entityType = ref(props.filters.entity_type ?? '')
const rule = ref(props.filters.rule ?? '')
const validation = ref('')
watch(
  () => props.filters,
  (value) => {
    severity.value = value.severity ?? ''
    organization.value = value.organization_id ?? ''
    entityType.value = value.entity_type ?? ''
    rule.value = value.rule ?? ''
  },
)
function apply() {
  const parsed = filtersSchema.safeParse({
    severity: severity.value || undefined,
    organization_id: organization.value || undefined,
    entity_type: entityType.value || undefined,
    rule: rule.value || undefined,
    status: 'open',
    page: 1,
    page_size: props.filters.page_size,
  })
  validation.value = parsed.success ? '' : 'Bitte eine gültige Organisations-UUID eingeben.'
  if (parsed.success) emit('apply', parsed.data)
}
</script>

<template>
  <form @submit.prevent="apply">
    <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-[1fr_1fr_1fr_1.5fr_auto]">
      <label
        ><span class="label">Schweregrad</span
        ><select v-model="severity" class="input">
          <option value="">Alle</option>
          <option value="error">Fehler</option>
          <option value="warning">Warnung</option>
          <option value="info">Hinweis</option>
        </select></label
      >
      <label
        ><span class="label">Objektart</span
        ><select v-model="entityType" class="input">
          <option value="">Alle verfügbaren</option>
          <option value="venue">Venue</option>
        </select></label
      >
      <label
        ><span class="label">Regel</span
        ><select v-model="rule" class="input">
          <option value="">Alle verfügbaren</option>
          <option value="venue_missing_geolocation">Geoposition fehlt</option>
        </select></label
      >
      <label
        ><span class="label">Organisation (UUID)</span
        ><input
          v-model.trim="organization"
          class="input"
          placeholder="Alle Organisationen"
          :aria-invalid="!!validation"
          aria-describedby="organization-help"
      /></label>
      <button type="submit" class="button-primary self-end">Anwenden</button>
    </div>
    <p id="organization-help" class="mt-3 text-xs text-slate-500">
      Status: offene Live-Befunde. Organisationsnamen-Suche, Veröffentlichungsfilter und
      gespeicherte Reviews sind noch nicht verfügbar.
    </p>
    <p v-if="validation" role="alert" class="mt-2 text-sm text-rose-700">{{ validation }}</p>
  </form>
</template>
