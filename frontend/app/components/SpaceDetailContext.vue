<script setup lang="ts">
import { computed } from 'vue'
import type { EntityDetail } from '#shared/contracts'
const props = defineProps<{ data: EntityDetail }>()
// Space→venue is the only venue relation in the verified contract. Never build a link from a name.
const venueAction = computed(() => {
  const venues = props.data.related.items.filter((item) => item.entity_type === 'venue')
  const venue = venues.length === 1 ? venues[0] : undefined
  return venue?.action?.entity_type === 'venue' && venue.action.entity_key === venue.entity_key
    ? venue.action
    : null
})
</script>

<template>
  <dl class="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2">
    <div v-if="data.item.facts.venue_name?.trim()">
      <dt class="type-metadata">Zugehöriger Ort</dt>
      <dd class="type-body break-words font-semibold">
        <NuxtLink v-if="venueAction" :to="venueAction.href" class="action-link">{{
          data.item.facts.venue_name
        }}</NuxtLink>
        <template v-else>{{ data.item.facts.venue_name }}</template>
      </dd>
    </div>
    <div v-if="data.item.organization_name?.trim()">
      <dt class="type-metadata">Organisation</dt>
      <dd class="type-body break-words">{{ data.item.organization_name }}</dd>
    </div>
  </dl>
</template>
