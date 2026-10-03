<script setup lang="ts">
import { ref } from 'vue'
import ResearchSqlEditorModal from './sql/ResearchSqlEditorModal.vue'
import type { ResearchExecutionResponse } from '#shared/contracts'
import { formatGroupingCoordinate, researchMetricLabels } from '~/utils/research-answer'
import { researchKey, researchHref } from '~/utils/research'
const props = defineProps<{ response: ResearchExecutionResponse }>()
defineEmits<{ adjust: [text?: string] }>()
const sqlEditor = ref<InstanceType<typeof ResearchSqlEditorModal> | null>(null)
const result = computed(() => props.response.result)
const plan = computed(() => props.response.plan.plan)
const structuredEvents = computed(
  () => plan.value.entity_type === 'event' && !props.response.execution.semantic,
)
const metric = computed(() =>
  'metric' in result.value ? researchMetricLabels[result.value.metric] : 'Datensätze',
)
const planMetric = computed(() => {
  const value = plan.value.metric
  const operation = typeof value === 'object' ? value?.operation : value
  if (operation === 'distinct_count') return 'Unterschiedliche Werte'
  if (operation === 'value') {
    return typeof value === 'object' && value?.field
      ? { start_date: 'Startdatum', longitude: 'Längengrad', latitude: 'Breitengrad' }[value.field]
      : 'Feldwert'
  }
  return operation && operation !== 'none' ? researchMetricLabels[operation] : 'Keine'
})
const number = (value: number) => value.toLocaleString('de-DE')
const date = (value: string | null) => (value ? value.split('-').reverse().join('.') : 'offen')
const period = computed(() => {
  const e = props.response.execution
  return e.from_date || e.to_date
    ? `${date(e.from_date)} – ${date(e.to_date)}`
    : 'Kein Datumsfilter'
})
const area = computed(
  () => props.response.resolution.find((item) => item.field === 'area_query')?.target.label,
)
const clarification = computed(() => {
  const r = result.value
  if (r.kind !== 'needs_clarification') return ''
  if (r.planner_state === 'needs_date') return 'Welchen Zeitraum meinst du?'
  if (r.planner_state === 'needs_location') return 'Welchen Ort meinst du?'
  if (r.planner_state === 'needs_criteria')
    return 'Welche Vergleichskriterien möchtest du verwenden?'
  if (r.reason === 'no_match')
    return `Keine eindeutige Zuordnung für „${r.query ?? 'diese Angabe'}“. Bitte präzisiere die Frage.`
  if (r.reason === 'taxonomy_conflict')
    return 'Das Genre gehört nicht zum gewählten Veranstaltungstyp. Bitte präzisiere die Auswahl.'
  if (r.reason === 'duplicate_target') return 'Bitte verwende unterschiedliche Vergleichsziele.'
  return `Welche Zuordnung meinst du${r.query ? ` mit „${r.query}“` : ''}?`
})
const dimensionLabels = {
  event: 'Veranstaltung',
  venue: 'Ort',
  organization: 'Organisation',
  category: 'Kategorie',
  genre: 'Genre',
  event_type: 'Veranstaltungstyp',
  month: 'Monat',
  municipality: 'Gemeinde',
  district: 'Kreis',
  state: 'Bundesland',
  country: 'Staat',
  region: 'Region',
}
const fieldLabels = {
  place_query: 'Ort',
  location_context: 'Standort',
  area_query: 'Gebiet',
  venue_query: 'Veranstaltungsort',
  organization_query: 'Organisation',
  event_type_queries: 'Veranstaltungstyp',
  category_queries: 'Kategorie',
  genre_queries: 'Genre',
  comparison_targets: 'Vergleichsziel',
}
</script>
<template>
  <section class="space-y-3" aria-label="Antwort">
    <ResearchSqlEditorModal
      v-if="response.sql_provenance.length"
      ref="sqlEditor"
      :statements="response.sql_provenance"
      :semantic="response.execution.semantic"
    />
    <div class="space-y-2 rounded-lg border border-slate-200 bg-slate-50/60 p-4">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h3 class="type-section-title">
          {{ result.kind === 'needs_clarification' ? 'Frage präzisieren' : 'Antwort' }}
        </h3>
        <button
          v-if="response.sql_provenance.length"
          class="button"
          aria-label="SQL Editor"
          @click="sqlEditor?.open()"
        >
          <AppIcon name="code" :size="14" />SQL Editor
        </button>
      </div>
      <template v-if="result.kind === 'count'">
        <p class="text-2xl font-semibold tabular-nums" data-testid="research-count">
          {{ number(result.value) }} {{ metric }}
        </p>
      </template>
      <template v-else-if="result.kind === 'taxonomy'">
        <p>
          {{ number(result.total) }} verwendete
          {{
            { genre: 'Genres', category: 'Kategorien', event_type: 'Veranstaltungstypen' }[
              result.taxonomy
            ]
          }}<span v-if="result.total > result.items.length">
            · {{ result.items.length }} angezeigt</span
          >
        </p>
        <ul class="space-y-1" aria-label="Taxonomie">
          <li v-for="item in result.items" :key="item.key">
            {{ item.name }} – {{ number(item.event_count) }} Veranstaltungen
          </li>
        </ul>
      </template>
      <template v-else-if="result.kind === 'spatial'">
        <p v-if="result.items[0]">
          {{
            result.spatial_metric === 'longitude'
              ? result.ordering === 'asc'
                ? 'Westlichster'
                : 'Östlichster'
              : result.ordering === 'asc'
                ? 'Südlichster'
                : 'Nördlichster'
          }}
          Treffer: „{{ result.items[0].name }}“<span v-if="result.items[0].city">
            in {{ result.items[0].city }}</span
          >
          bei {{ result.items[0].location?.[result.spatial_metric] }}°
          {{ result.spatial_metric === 'longitude' ? 'Länge' : 'Breite' }}.
        </p>
        <p v-else>Keine passenden Datensätze mit bekannter Position.</p>
      </template>
      <p v-else-if="result.kind === 'aggregate'">
        {{ metric }} nach
        {{
          {
            month: 'Monat',
            event: 'Veranstaltung',
            venue: 'Veranstaltungsort',
            organization: 'Organisation',
            category: 'Kategorie',
            genre: 'Genre',
            event_type: 'Veranstaltungstyp',
            municipality: 'Gemeinde',
            district: 'Kreis',
            state: 'Bundesland',
            country: 'Staat',
            region: 'Region',
          }[result.group_by]
        }}
        · {{ result.items.length }} gelieferte Gruppen (höchstens 20)
      </p>
      <p v-else-if="result.kind === 'comparison'">Vergleich: {{ metric }}</p>
      <template v-else-if="result.kind === 'records'">
        <p v-if="structuredEvents">
          Sortierung: Datum {{ plan.ordering === 'desc' ? 'absteigend' : 'aufsteigend' }}
        </p>
        <p v-if="plan.limit !== null">Maximal {{ plan.limit }} Ergebnisse</p>
        <p v-if="result.total !== null">
          {{ number(result.total) }} Ergebnisse insgesamt · {{ result.items.length }} angezeigt
        </p>
        <template v-else-if="response.execution.semantic">
          <p>Semantische Relevanzsuche · bis zu {{ plan.limit ?? 20 }} Treffer</p>
          <p class="text-sm text-slate-600">
            {{ result.items.length }} angezeigte Treffer. Keine vollständige Zählung aller passenden
            Datensätze.
          </p>
        </template>
        <p v-else>{{ result.items.length }} Ergebnisse angezeigt</p>
      </template>
      <template v-else-if="result.kind === 'needs_clarification'">
        <p>{{ clarification }}</p>
        <p class="text-sm text-slate-600">Passe die Frage an und sende sie erneut ab.</p>
        <div
          v-if="result.candidates.length"
          class="flex flex-wrap gap-2"
          aria-label="Mögliche Zuordnungen"
        >
          <button
            v-for="candidate in result.candidates"
            :key="`${candidate.entity_type}:${candidate.id}`"
            class="button"
            @click="$emit('adjust', candidate.label)"
          >
            {{ candidate.label }}
          </button>
        </div>
        <button class="action-link" @click="$emit('adjust')">Frage anpassen</button>
      </template>
      <template v-if="result.kind !== 'needs_clarification'">
        <p class="text-sm text-slate-600">
          {{
            area
              ? `${response.execution.area_relation === 'outside' ? 'Außerhalb: ' : ''}${area} · `
              : ''
          }}{{ period
          }}<span v-if="response.execution.time_from">
            · ab {{ response.execution.time_from }} Uhr</span
          >
        </p>
        <p
          v-if="response.execution.time_of_day && response.execution.time_of_day !== 'none'"
          class="text-sm text-slate-600"
        >
          Tageszeit:
          {{
            {
              morning: '06:00–12:00',
              afternoon: '12:00–18:00',
              evening: '18:00–22:00',
              night: '22:00–06:00',
            }[response.execution.time_of_day]
          }}
          (Ende ausgeschlossen, {{ response.timezone }})
        </p>
        <p
          v-for="item in response.resolution.filter((item) =>
            ['genre_queries', 'event_type_queries', 'category_queries'].includes(item.field),
          )"
          :key="`${item.field}:${item.target.id}`"
          class="text-sm text-slate-600"
        >
          {{ fieldLabels[item.field] }}: {{ item.target.label }}
        </p>
        <p
          v-if="response.execution.structured && !response.execution.semantic"
          class="text-sm font-medium text-blue-800"
        >
          Exakte strukturierte Auswertung
        </p>
        <p v-else-if="response.execution.semantic && result.kind !== 'records'" class="text-sm">
          Semantische Relevanz
        </p>
      </template>
    </div>
    <div v-if="result.kind === 'grouped'" class="space-y-2 overflow-x-auto">
      <p>
        {{ metric }} je Gruppenkombination · {{ result.items.length }} von höchstens
        {{ result.limit }} Gruppen
      </p>
      <table class="w-full text-left text-sm" aria-label="Mehrdimensionale Auswertung">
        <thead>
          <tr class="border-b">
            <th v-for="dimension in result.dimensions" :key="dimension" scope="col" class="p-2">
              {{ dimensionLabels[dimension] }}
            </th>
            <th scope="col" class="p-2 text-right">{{ metric }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in result.items"
            :key="JSON.stringify(item.coordinates.map((c) => c.key))"
            class="border-b"
          >
            <template v-for="(coordinate, index) in item.coordinates" :key="coordinate.dimension">
              <th v-if="index === 0" scope="row" class="p-2 font-normal">
                {{ formatGroupingCoordinate(coordinate.dimension, coordinate.name) }}
              </th>
              <td v-else class="p-2">
                {{ formatGroupingCoordinate(coordinate.dimension, coordinate.name) }}
              </td>
            </template>
            <td class="p-2 text-right tabular-nums">{{ number(item.value) }}</td>
          </tr>
        </tbody>
      </table>
      <EmptyState v-if="!result.items.length" message="Keine Gruppen für diese Auswertung." />
    </div>
    <div v-if="result.kind === 'aggregate' || result.kind === 'comparison'" class="overflow-x-auto">
      <table class="w-full text-left text-sm" aria-label="Auswertung">
        <thead>
          <tr class="border-b">
            <th scope="col" class="p-2">
              {{ result.kind === 'comparison' ? 'Vergleichsziel' : 'Gruppe' }}
            </th>
            <th scope="col" class="p-2 text-right">{{ metric }}</th>
          </tr>
        </thead>
        <tbody v-if="result.kind === 'aggregate'">
          <tr v-for="item in result.items" :key="item.key" class="border-b">
            <th scope="row" class="p-2 font-normal">
              <NuxtLink
                v-if="result.group_by === 'event'"
                :to="`/research/events/${item.key}`"
                class="underline"
              >
                {{ item.name }}
              </NuxtLink>
              <template v-else>{{ item.name }}</template>
            </th>
            <td class="p-2 text-right tabular-nums">{{ number(item.value) }}</td>
          </tr>
        </tbody>
        <tbody v-else>
          <tr
            v-for="item in result.items"
            :key="`${item.target.entity_type}:${item.target.id}`"
            class="border-b"
          >
            <th scope="row" class="p-2 font-normal">{{ item.target.label }}</th>
            <td class="p-2 text-right tabular-nums">{{ number(item.value) }}</td>
          </tr>
        </tbody>
      </table>
      <EmptyState v-if="!result.items.length" message="Keine Gruppen für diese Auswertung." />
    </div>
    <div v-if="result.kind === 'records' || result.kind === 'spatial'" class="space-y-2">
      <EmptyState
        v-if="!result.items.length"
        :message="
          response.execution.semantic
            ? 'Keine ausreichend passenden Veranstaltungen gefunden.'
            : 'Keine passenden Datensätze gefunden.'
        "
      />
      <ResearchResult
        v-for="item in result.items"
        :key="researchKey(item)"
        :item="item"
        :semantic="response.execution.semantic"
        :show-full-date="true"
        @select="navigateTo(researchHref(item.entity_type, item.entity_key))"
      />
    </div>
    <details class="rounded-lg border border-slate-200 p-3 text-sm">
      <summary class="cursor-pointer font-medium">So wurde die Frage verstanden</summary>
      <dl class="mt-3 grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 break-words">
        <dt>Absicht</dt>
        <dd>{{ plan.intent }}</dd>
        <dt>Datensatztyp</dt>
        <dd>{{ plan.entity_type }}</dd>
        <dt>Metrik</dt>
        <dd>{{ planMetric }}</dd>
        <template v-for="(item, index) in response.resolution" :key="index"
          ><dt>{{ fieldLabels[item.field] }}</dt>
          <dd>{{ item.target.label }}</dd></template
        >
        <dt>Zeitraum</dt>
        <dd>{{ period }}</dd>
        <dt v-if="response.execution.time_from">Uhrzeit ab</dt>
        <dd v-if="response.execution.time_from">{{ response.execution.time_from }}</dd>
        <dt>Kategorie-IDs</dt>
        <dd>{{ response.execution.category_ids.join(', ') || 'Keine' }}</dd>
        <dt>Genre-Schlüssel</dt>
        <dd>{{ response.execution.genre_keys.join(', ') || 'Keine' }}</dd>
        <dt>Strukturiert</dt>
        <dd>{{ response.execution.structured ? 'Ja' : 'Nein' }}</dd>
        <dt>Semantische Relevanz</dt>
        <dd>{{ response.execution.semantic ? 'Ja' : 'Nein' }}</dd>
        <dt>Datenstand</dt>
        <dd>
          <time :datetime="response.observed_at">{{ response.observed_at }}</time>
        </dd>
        <dt>Zeitzone</dt>
        <dd>{{ response.timezone }}</dd>
        <dt>Laufzeit (ms)</dt>
        <dd>
          Planung {{ response.diagnostics.planner_ms }} · Zuordnung
          {{ response.diagnostics.resolution_ms }} · Ausführung
          {{ response.diagnostics.execution_ms }} · Gesamt {{ response.diagnostics.total_ms }}
        </dd>
      </dl>
    </details>
  </section>
</template>
