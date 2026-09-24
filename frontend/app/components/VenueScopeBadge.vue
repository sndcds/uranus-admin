<script setup lang="ts">
import type { VenueScope } from '#shared/contracts'
import { venueScopeLabels } from '~/utils/venues'
import StatusBadge from './StatusBadge.vue'

defineProps<{ scope: VenueScope }>()
</script>

<template>
  <StatusBadge
    :label="venueScopeLabels[scope]"
    class="min-w-0 whitespace-normal [overflow-wrap:anywhere]"
    :data-venue-scope="scope"
  />
</template>
