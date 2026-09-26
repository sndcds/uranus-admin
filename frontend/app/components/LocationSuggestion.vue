<script setup lang="ts">
import { computed, nextTick, ref, watch, type ComponentPublicInstance } from 'vue'
import type { GeocodeRequestDetail } from '#shared/contracts'
import { geocodeMessages, matchReasonLabels } from '~/utils/geocoding'
import { recordDateTime } from '~/utils/presentation'

const props = defineProps<{ suggestion: GeocodeRequestDetail }>()
const selectedId = ref('')
const candidateMap = ref<{ focusCandidate: (id: string, reveal?: boolean) => void }>()
const candidateRows = new Map<string, HTMLElement>()

const showCandidates = computed(
  () =>
    ['candidate', 'ambiguous'].includes(props.suggestion.status) &&
    props.suggestion.candidates.length > 0,
)
const bestId = computed(() => props.suggestion.best_candidate?.id ?? '')
const multiple = computed(() => props.suggestion.candidates.length > 1)

function showOnMap(id: string) {
  void select(id)
  candidateMap.value?.focusCandidate(id, true)
}

function resetSelection() {
  selectedId.value =
    props.suggestion.candidates.find((candidate) => candidate.id === bestId.value)?.id ||
    props.suggestion.candidates[0]?.id ||
    ''
}

function rowRef(id: string, element: Element | ComponentPublicInstance | null) {
  if (element instanceof HTMLElement) candidateRows.set(id, element)
  else candidateRows.delete(id)
}

async function select(id: string, focus = false) {
  selectedId.value = id
  if (focus) {
    await nextTick()
    candidateRows.get(id)?.focus({ preventScroll: true })
    candidateRows.get(id)?.scrollIntoView({ block: 'nearest' })
  }
}

watch(
  () => [
    props.suggestion.id,
    props.suggestion.generation,
    bestId.value,
    ...props.suggestion.candidates.map((candidate) => candidate.id),
  ],
  resetSelection,
  {
    immediate: true,
  },
)
</script>

<template>
  <RecordSection title="Standortprüfung">
    <p class="type-metadata">
      Letzte Prüfung:
      <time
        v-if="suggestion.checked_at"
        :datetime="suggestion.checked_at"
        :title="suggestion.checked_at"
        >{{ recordDateTime(suggestion.checked_at) }}</time
      >
      <span v-else>Noch nicht geprüft</span>
    </p>
    <InlineAlert
      v-if="['ambiguous', 'insufficient_input', 'failed', 'stale'].includes(suggestion.status)"
      :tone="suggestion.status === 'failed' ? 'error' : 'warning'"
    >
      {{ geocodeMessages[suggestion.status] }}
    </InlineAlert>
    <p
      v-else
      class="type-body"
      :role="['pending', 'checking'].includes(suggestion.status) ? 'status' : undefined"
    >
      {{ geocodeMessages[suggestion.status] }}
    </p>
    <EmptyState
      v-if="!showCandidates && !['pending', 'checking'].includes(suggestion.status)"
      compact
      message="Keine aktuellen Kartenpositionen verfügbar."
    />
    <div
      v-if="showCandidates"
      class="panel overflow-hidden"
      :class="multiple ? 'xl:grid xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]' : ''"
      data-candidate-comparison
    >
      <CandidateMap
        ref="candidateMap"
        embedded
        :candidates="suggestion.candidates"
        :selected-id="selectedId"
        @select="select($event, true)"
      />
      <ul
        class="min-w-0 divide-y divide-slate-200 border-t border-slate-200"
        :class="multiple ? 'xl:max-h-[32rem] xl:overflow-y-auto xl:border-t-0 xl:border-l' : ''"
        aria-label="Standortkandidaten"
      >
        <li
          v-for="candidate in suggestion.candidates"
          :key="candidate.id"
          :ref="(element) => rowRef(candidate.id, element)"
          tabindex="-1"
          class="min-w-0 space-y-2 border-l-4 p-4 outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-fuchsia-700"
          :class="
            candidate.id === selectedId
              ? 'border-fuchsia-700 bg-fuchsia-50/40'
              : 'border-transparent'
          "
          :aria-current="candidate.id === selectedId ? 'true' : undefined"
          @click="select(candidate.id)"
        >
          <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span v-if="multiple && candidate.id === bestId" class="type-metadata"
              >{{ candidate.rank }} ·</span
            >
            <span class="font-semibold text-slate-900">{{
              candidate.id === bestId
                ? 'Bester automatischer Treffer'
                : `Kandidat ${candidate.rank}`
            }}</span>
            <span class="type-metadata">{{ candidate.id === selectedId ? 'Ausgewählt' : '' }}</span>
          </div>
          <h4 class="type-row-title break-words">{{ candidate.display_name }}</h4>
          <div
            :class="multiple ? '' : 'sm:grid sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] sm:gap-4'"
          >
            <p class="type-body font-medium">
              {{ Math.round(candidate.match_score * 100) }} % Adressübereinstimmung
            </p>
            <ul
              class="type-metadata mt-2 grid grid-cols-2 gap-x-3 gap-y-1"
              :class="multiple ? '' : 'sm:mt-0'"
              aria-label="Adressabgleich"
            >
              <li v-for="reason in candidate.match_reasons" :key="reason" class="flex gap-1.5">
                <span aria-hidden="true">{{ reason.endsWith('_exact') ? '✓' : '–' }}</span
                ><span>{{ matchReasonLabels[reason] }}</span>
              </li>
            </ul>
          </div>
          <div class="flex flex-wrap items-center gap-x-4">
            <p class="type-metadata break-all font-mono">
              <span class="sr-only">Koordinaten: </span>{{ candidate.latitude.toFixed(6) }},
              {{ candidate.longitude.toFixed(6) }}
            </p>
            <button
              v-if="multiple"
              type="button"
              class="action-link"
              :aria-pressed="candidate.id === selectedId"
              :aria-label="`Kandidat ${candidate.rank} auf der Karte zeigen`"
              @click.stop="showOnMap(candidate.id)"
            >
              Auf Karte zeigen
            </button>
            <a
              :href="candidate.osm_url"
              target="_blank"
              rel="noopener noreferrer"
              referrerpolicy="no-referrer"
              class="action-link"
              :aria-label="`Kandidat ${candidate.rank} auf OpenStreetMap öffnen (neuer Tab)`"
              @click.stop
              >OpenStreetMap öffnen <AppIcon name="external" :size="13"
            /></a>
          </div>
        </li>
      </ul>
    </div>
  </RecordSection>
</template>
