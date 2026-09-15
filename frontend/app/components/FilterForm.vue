<script setup lang="ts">
import type { FindingFilters } from '#shared/contracts'
import { filtersSchema, statusSchema } from '#shared/contracts'
const props = defineProps<{ filters: FindingFilters }>()
const emit = defineEmits<{ apply: [filters: FindingFilters] }>()
const severity = ref(props.filters.severity ?? '')
const organization = ref(props.filters.organization_id ?? '')
const entityType = ref(props.filters.entity_type ?? '')
const rule = ref(props.filters.rule ?? '')
const mode = ref(props.filters.mode)
const status = ref(props.filters.status ?? '')
const validation = ref('')
watch(
  () => props.filters,
  (value) => {
    severity.value = value.severity ?? ''
    organization.value = value.organization_id ?? ''
    entityType.value = value.entity_type ?? ''
    rule.value = value.rule ?? ''
    mode.value = value.mode
    status.value = value.status ?? ''
  },
)
function apply() {
  const parsed = filtersSchema.safeParse({
    severity: severity.value || undefined,
    organization_id: organization.value || undefined,
    entity_type: entityType.value || undefined,
    rule: rule.value || undefined,
    mode: mode.value,
    status: status.value || undefined,
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
          <option
            v-for="kind in [
              'organization',
              'venue',
              'space',
              'event',
              'event_date',
              'event_link',
              'license',
              'image',
              'image_link',
              'partner_request',
              'team_membership',
              'user',
            ]"
            :key="kind"
            :value="kind"
          >
            {{ kind }}
          </option>
        </select></label
      >
      <label
        ><span class="label">Regel</span
        ><select v-model="rule" class="input">
          <option value="">Alle verfügbaren</option>
          <option value="venue_missing_geolocation">Geoposition fehlt</option>
          <option
            v-for="code in [
              'url_syntax',
              'event_without_dates',
              'event_without_location',
              'event_date_without_location',
              'event_date_space_venue_mismatch',
              'image_link_without_image',
              'image_link_unknown_context',
              'image_link_invalid_identifier',
              'image_link_missing_target',
              'image_orphaned_upload',
              'partner_self_request',
              'partner_missing_organization',
              'partner_missing_user',
              'partner_unknown_status',
              'partner_long_pending',
              'partner_accepted_without_grant',
              'team_invitation_old',
              'user_activation_old',
            ]"
            :key="code"
            :value="code"
          >
            {{ code }}
          </option>
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
      <label
        ><span class="label">Quelle</span
        ><select v-model="mode" class="input">
          <option value="live">Live-Diagnose (vollständige Prüfung)</option>
          <option value="persisted">Gespeicherte Befunde</option>
        </select></label
      >
      <label
        ><span class="label">Befundstatus</span
        ><select v-model="status" class="input">
          <option value="">Alle</option>
          <option v-for="value in statusSchema.options" :key="value" :value="value">
            {{ value }}
          </option>
        </select></label
      >
      <button type="submit" class="button-primary self-end">Anwenden</button>
    </div>
    <p id="organization-help" class="mt-3 text-xs text-slate-500">
      Reviews beziehen sich auf gespeicherte Befunde. Aktuelle Prüfungen zeigen den jetzigen
      Datenzustand.
    </p>
    <p v-if="validation" role="alert" class="mt-2 text-sm text-rose-700">{{ validation }}</p>
  </form>
</template>
