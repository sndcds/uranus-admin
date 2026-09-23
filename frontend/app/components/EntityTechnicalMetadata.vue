<script setup lang="ts">
import { computed } from 'vue'
import type { EntityDetail } from '#shared/contracts'
import TechnicalInfoBar from './TechnicalInfoBar.vue'
import { adminTimeZone, recordDateTime } from '~/utils/presentation'
import type { TechnicalFact } from '~/utils/operations'
const props = defineProps<{ data: EntityDetail }>()
const items = computed<TechnicalFact[]>(() => [
  { label: 'UUID', value: props.data.item.entity_key, mono: true, copyable: true },
  {
    label: 'Quelldatensatz angelegt',
    value: props.data.item.created_at ? recordDateTime(props.data.item.created_at) : null,
    datetime: props.data.item.created_at ?? undefined,
    timezone: adminTimeZone,
  },
  {
    label: 'Datenstand des Abrufs',
    value: recordDateTime(props.data.observed_at),
    datetime: props.data.observed_at,
    timezone: adminTimeZone,
  },
])
</script>

<template>
  <TechnicalInfoBar :items="items" />
</template>
