<script setup lang="ts">
import { computed } from 'vue'
import type { GeocodeCandidate } from '#shared/contracts'

const props = defineProps<{ candidates: GeocodeCandidate[]; selectedId: string }>()
const emit = defineEmits<{ select: [id: string] }>()

const points = computed(() => {
  const latitudes = props.candidates.map((candidate) => candidate.latitude)
  const longitudes = props.candidates.map((candidate) => candidate.longitude)
  const minLatitude = Math.min(...latitudes)
  const maxLatitude = Math.max(...latitudes)
  const minLongitude = Math.min(...longitudes)
  const maxLongitude = Math.max(...longitudes)
  const latitudeRange = maxLatitude - minLatitude
  const longitudeRange = maxLongitude - minLongitude
  return props.candidates.map((candidate) => ({
    candidate,
    left:
      longitudeRange === 0 ? 50 : 8 + ((candidate.longitude - minLongitude) / longitudeRange) * 84,
    top: latitudeRange === 0 ? 50 : 8 + ((maxLatitude - candidate.latitude) / latitudeRange) * 84,
  }))
})
</script>

<template>
  <section
    class="relative min-h-72 overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 sm:min-h-80"
    aria-label="Karte der Standortkandidaten"
  >
    <div
      aria-hidden="true"
      class="absolute inset-0 opacity-70"
      style="
        background-image:
          linear-gradient(#cbd5e1 1px, transparent 1px),
          linear-gradient(90deg, #cbd5e1 1px, transparent 1px);
        background-size: 25% 25%;
      "
    />
    <div
      class="absolute inset-x-3 top-3 flex items-start justify-between gap-3 text-xs text-slate-500"
    >
      <span>Relative Lage · Norden oben</span>
      <span>{{ candidates.length }} {{ candidates.length === 1 ? 'Kandidat' : 'Kandidaten' }}</span>
    </div>
    <div class="absolute inset-x-0 bottom-16 top-10">
      <button
        v-for="point in points"
        :key="point.candidate.id"
        type="button"
        class="absolute grid size-9 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-2 text-sm font-bold shadow-sm transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fuchsia-700"
        :class="
          point.candidate.id === selectedId
            ? 'z-20 border-fuchsia-800 bg-fuchsia-700 text-white'
            : 'z-10 border-slate-600 bg-white text-slate-800 hover:border-fuchsia-700'
        "
        :style="{ left: `${point.left}%`, top: `${point.top}%` }"
        :aria-label="`Kandidat ${point.candidate.rank} auf der Karte: ${point.candidate.display_name}`"
        :aria-pressed="point.candidate.id === selectedId"
        @click="emit('select', point.candidate.id)"
      >
        {{ point.candidate.rank }}
      </button>
    </div>
    <div class="absolute inset-x-3 bottom-3 flex flex-wrap items-end justify-between gap-2">
      <p class="rounded-md bg-white/90 px-2 py-1 text-xs text-slate-600">
        Prüfung ohne Kartenkacheln; die Kandidatenliste ist die vollständige Textansicht.
      </p>
      <OsmAttribution class="rounded-md bg-white/90 px-2 py-1 text-xs" />
    </div>
  </section>
</template>
