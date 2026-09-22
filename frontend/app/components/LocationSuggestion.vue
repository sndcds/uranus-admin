<script setup lang="ts">
import { computed, nextTick, ref, watch, type ComponentPublicInstance } from 'vue'
import type { GeocodeRequestDetail } from '#shared/contracts'
import { geocodeMessages, matchReasonLabels } from '~/utils/geocoding'

const props = defineProps<{ suggestion: GeocodeRequestDetail }>()
const selectedId = ref('')
const candidateRows = new Map<string, HTMLElement>()

const showCandidates = computed(
  () =>
    ['candidate', 'ambiguous'].includes(props.suggestion.status) &&
    props.suggestion.candidates.length > 0,
)
const bestId = computed(() => props.suggestion.best_candidate?.id ?? '')

function resetSelection() {
  selectedId.value = bestId.value || props.suggestion.candidates[0]?.id || ''
}

function rowRef(id: string, element: Element | ComponentPublicInstance | null) {
  if (element instanceof HTMLElement) candidateRows.set(id, element)
  else candidateRows.delete(id)
}

async function select(id: string, focus = false) {
  selectedId.value = id
  if (focus) {
    await nextTick()
    candidateRows.get(id)?.focus()
  }
}

watch(() => [props.suggestion.id, props.suggestion.generation, bestId.value], resetSelection, {
  immediate: true,
})
</script>

<template>
  <section class="space-y-3" aria-labelledby="candidate-heading">
    <SectionHeader
      title-id="candidate-heading"
      :title="showCandidates ? 'Kandidaten vergleichen' : 'Ergebnis der Standortprüfung'"
      :description="
        showCandidates
          ? 'Positionen, Adressübereinstimmung und Abweichungen im direkten Vergleich.'
          : undefined
      "
      as="h2"
    />

    <InlineAlert v-if="suggestion.status === 'ambiguous'" tone="warning">
      Mehrere mögliche Standorte wurden gefunden. Bitte die Kandidaten vergleichen.
    </InlineAlert>
    <InlineAlert v-else-if="suggestion.status === 'candidate'" tone="info">
      Standortvorschlag vorhanden. Die gespeicherte Geoposition in Kulturbytes wird dadurch nicht
      verändert.
    </InlineAlert>
    <EmptyState
      v-else-if="suggestion.status === 'not_found'"
      message="Für diese Adresse wurde kein passender Standort gefunden."
    />
    <InlineAlert v-else-if="suggestion.status === 'insufficient_input'" tone="warning">
      Für eine zuverlässige Standortsuche fehlen ausreichende Adressdaten. Bitte die Quelldaten des
      betroffenen Datensatzes prüfen.
    </InlineAlert>
    <InlineAlert v-else-if="suggestion.status === 'failed'" tone="error">
      Standortprüfung fehlgeschlagen. Die Prüfung kann im Workflowbereich erneut eingeplant werden.
    </InlineAlert>
    <InlineAlert v-else-if="suggestion.status === 'pending'" tone="info">
      Prüfung vorgemerkt. Der Worker hat diesen Auftrag noch nicht abgeschlossen.
    </InlineAlert>
    <InlineAlert v-else-if="suggestion.status === 'checking'" tone="info">
      Prüfung läuft. Der aktuelle Prüfstand kann unten aktualisiert werden.
    </InlineAlert>
    <InlineAlert v-else tone="warning">{{ geocodeMessages[suggestion.status] }}</InlineAlert>

    <template v-if="showCandidates">
      <CandidateMap
        :candidates="suggestion.candidates"
        :selected-id="selectedId"
        @select="select($event, true)"
      />
      <DataListShell as="ul" class="divide-y divide-slate-100" aria-label="Standortkandidaten">
        <li
          v-for="candidate in suggestion.candidates"
          :key="candidate.id"
          :ref="(element) => rowRef(candidate.id, element)"
          tabindex="-1"
          class="data-row grid gap-3 outline-none transition-colors md:grid-cols-[2.5rem_minmax(0,1fr)_auto]"
          :class="candidate.id === selectedId ? 'bg-fuchsia-50/60' : ''"
          :aria-current="candidate.id === selectedId ? 'true' : undefined"
          @click="select(candidate.id)"
        >
          <span
            class="grid size-8 place-items-center rounded-full bg-slate-100 text-sm font-bold text-slate-700"
            aria-hidden="true"
            >{{ candidate.rank }}</span
          >
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <h3 class="break-words text-sm font-semibold text-slate-900">
                {{ candidate.display_name }}
              </h3>
              <StatusBadge
                v-if="candidate.id === bestId"
                label="Bester automatischer Treffer"
                tone="success"
              />
            </div>
            <p class="mt-1 text-sm font-medium text-slate-700">
              {{ Math.round(candidate.match_score * 100) }} % Adressübereinstimmung
            </p>
            <ul class="mt-2 grid gap-x-4 gap-y-1 text-xs text-slate-600 sm:grid-cols-2">
              <li v-for="reason in candidate.match_reasons" :key="reason" class="flex gap-1.5">
                <span aria-hidden="true">{{ reason.endsWith('_exact') ? '✓' : '–' }}</span>
                <span>{{ matchReasonLabels[reason] }}</span>
              </li>
            </ul>
            <p class="mt-2 break-all font-mono text-xs text-slate-500">
              {{ candidate.latitude.toFixed(6) }}, {{ candidate.longitude.toFixed(6) }}
            </p>
          </div>
          <div
            class="flex flex-wrap items-start gap-x-4 gap-y-2 text-xs md:max-w-44 md:justify-end"
          >
            <button
              type="button"
              class="rounded font-semibold text-fuchsia-700 underline-offset-4 hover:underline"
              :aria-pressed="candidate.id === selectedId"
              :aria-label="`Kandidat ${candidate.rank} auf der Karte zeigen`"
              @click.stop="select(candidate.id)"
            >
              Auf Karte zeigen
            </button>
            <a
              :href="candidate.osm_url"
              target="_blank"
              rel="noopener noreferrer"
              referrerpolicy="no-referrer"
              class="inline-flex items-center gap-1 rounded text-fuchsia-700 underline-offset-4 hover:underline"
              :aria-label="`Kandidat ${candidate.rank} auf OpenStreetMap öffnen (neuer Tab)`"
              @click.stop
              >OpenStreetMap öffnen <AppIcon name="external" :size="13"
            /></a>
          </div>
        </li>
      </DataListShell>
    </template>
  </section>
</template>
