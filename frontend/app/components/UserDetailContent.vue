<script setup lang="ts">
import { computed } from 'vue'
import type { EntityDetail } from '#shared/contracts'
import { activityStatus } from '~/utils/activity'
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
  <div class="operations-grid" data-record-info-grid>
    <RecordSection v-if="status" title="Benutzerinformationen" surface="panel">
      <CompactFacts :items="[{ label: 'Kontostatus', value: status }]" />
    </RecordSection>
    <RecordSection title="Teamkontext" surface="panel">
      <CompactFacts
        :items="[
          {
            label: 'Teammitgliedschaften',
            value: data.item.facts.memberships,
            description: 'Einschließlich Einladungen',
          },
        ]"
      />
    </RecordSection>
  </div>
  <RecordRelations :data="data" :loading="loading">
    <template #description>
      Gemeinsame Liste nach Objektart und Name. „Eingeladen“ und „Beigetreten“ bezeichnen den
      Mitgliedsstatus; ein Einladungszeitpunkt ist kein Beitrittszeitpunkt.
    </template>
  </RecordRelations>
  <RecordWorkflowSummary :item="data.item" />
</template>
