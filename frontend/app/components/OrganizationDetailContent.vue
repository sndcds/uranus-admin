<script setup lang="ts">
import { computed } from 'vue'
import type { EntityDetail } from '#shared/contracts'
import { metric } from '~/utils/presentation'
const props = defineProps<{ data: EntityDetail; loading: boolean }>()
const facts = computed(() => [
  { label: 'Veranstaltungen', value: props.data.item.facts.events },
  { label: 'Orte', value: props.data.item.facts.venues },
  {
    label: 'Teammitgliedschaften',
    value: props.data.item.facts.memberships,
    note: 'Einschließlich Einladungen',
  },
])
</script>

<template>
  <RecordSection title="Auf einen Blick">
    <dl class="grid gap-4 sm:grid-cols-3">
      <div v-for="fact in facts" :key="fact.label" class="min-w-0">
        <dt class="type-metadata">{{ fact.label }}</dt>
        <dd class="type-body mt-1 break-words font-semibold">{{ metric(fact.value) }}</dd>
        <dd v-if="fact.note" class="type-metadata">{{ fact.note }}</dd>
      </div>
    </dl>
  </RecordSection>
  <RecordLocation :item="data.item" />
  <RecordRelations :data="data" :loading="loading" />
  <RecordWorkflowSummary :item="data.item" />
</template>
