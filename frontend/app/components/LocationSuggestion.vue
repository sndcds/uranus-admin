<script setup lang="ts">
import type { GeocodeRequestDetail } from '#shared/contracts'
import { geocodeMessages, matchReasonLabels } from '~/utils/geocoding'
defineProps<{ suggestion: GeocodeRequestDetail }>()
</script>
<template>
  <div class="space-y-4">
    <h2 class="text-lg font-semibold">Standortvorschlag</h2>
    <p role="status">{{ geocodeMessages[suggestion.status] }}</p>
    <p class="muted">
      Dies sind Vorschläge anhand der Adresse. Die gespeicherte Geoposition in Kulturbytes wird
      dadurch nicht verändert.
    </p>
    <ul class="space-y-3" aria-label="Standortkandidaten">
      <li
        v-for="candidate in suggestion.candidates"
        :key="candidate.id"
        class="panel p-4 space-y-2 break-words"
      >
        <h3 class="font-semibold">{{ candidate.display_name }}</h3>
        <p>{{ candidate.latitude.toFixed(6) }}, {{ candidate.longitude.toFixed(6) }}</p>
        <p>Übereinstimmung: {{ Math.round(candidate.match_score * 100) }} %</p>
        <ul class="text-sm text-slate-600">
          <li v-for="reason in candidate.match_reasons" :key="reason">
            {{ matchReasonLabels[reason] }}
          </li>
        </ul>
        <a
          :href="candidate.osm_url"
          target="_blank"
          rel="noopener noreferrer"
          class="text-fuchsia-700 underline"
          >Auf OpenStreetMap ansehen</a
        >
      </li>
    </ul>
    <OsmAttribution />
  </div>
</template>
