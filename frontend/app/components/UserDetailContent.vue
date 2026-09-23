<script setup lang="ts">
import { computed } from 'vue'
import type { EntityDetail } from '#shared/contracts'
import { activityStatus } from '~/utils/activity'
import { metric } from '~/utils/presentation'
const props = defineProps<{ data: EntityDetail; loading: boolean }>()
// The server owns the canonical label. Only suppress identical context values here.
const identity = computed(() => {
  const seen = new Set([props.data.item.entity_name.trim()])
  return [
    { label: 'E-Mail', value: props.data.item.email },
    { label: 'Benutzername', value: props.data.item.facts.username },
  ].filter(({ value }) => {
    if (!value?.trim() || seen.has(value.trim())) return false
    seen.add(value.trim())
    return true
  })
})
const status = computed(() => activityStatus(props.data.item.status))
</script>

<template>
  <EntityHero :item="data.item" section="users">
    <template #context>
      <p v-for="field in identity" :key="field.label" class="type-body mt-2 break-words">
        <span class="type-metadata">{{ field.label }}:</span> {{ field.value }}
      </p>
    </template>
  </EntityHero>
  <RecordSection v-if="status" title="Benutzerinformationen">
    <dl>
      <dt class="type-metadata">Kontostatus</dt>
      <dd class="type-body mt-1">{{ status }}</dd>
    </dl>
  </RecordSection>
  <RecordSection title="Teamkontext">
    <dl>
      <dt class="type-metadata">Teammitgliedschaften</dt>
      <dd class="type-body mt-1 font-semibold">{{ metric(data.item.facts.memberships) }}</dd>
      <dd class="type-metadata">Einschließlich Einladungen</dd>
    </dl>
  </RecordSection>
  <RecordRelations :data="data" :loading="loading">
    <template #description>
      Gemeinsame Liste nach Objektart und Name. „Eingeladen“ und „Beigetreten“ bezeichnen den
      Mitgliedsstatus; ein Einladungszeitpunkt ist kein Beitrittszeitpunkt.
    </template>
  </RecordRelations>
  <RecordWorkflowSummary :item="data.item" />
</template>
