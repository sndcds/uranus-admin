<script setup lang="ts">
import { computed } from 'vue'
import type { EntityDetail } from '#shared/contracts'
import { activityMapUrl, activityName } from '~/utils/activity'
const props = defineProps<{ item: EntityDetail['item'] }>()
const mapUrl = computed(() => activityMapUrl(props.item.location))
</script>

<template>
  <RecordSection
    v-if="item.address?.trim() || mapUrl"
    :title="item.address?.trim() ? 'Adresse' : 'Standort'"
    surface="panel"
  >
    <p v-if="item.address?.trim()" class="type-body max-w-[72ch] whitespace-pre-line break-words">
      {{ item.address }}
    </p>
    <a
      v-if="mapUrl"
      :href="mapUrl"
      class="action-link"
      target="_blank"
      rel="noopener noreferrer"
      referrerpolicy="no-referrer"
      :aria-label="`${activityName(item)} auf OpenStreetMap öffnen (neuer Tab)`"
    >
      Auf OpenStreetMap öffnen <AppIcon name="external" :size="16" />
    </a>
  </RecordSection>
</template>
