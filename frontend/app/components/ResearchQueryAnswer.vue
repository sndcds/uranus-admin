<script setup lang="ts">
import type { ResearchExecutionResponse } from '#shared/contracts'
import { researchMetricLabels } from '~/utils/research-answer'
import { researchKey, researchHref } from '~/utils/research'
const props = defineProps<{ response: ResearchExecutionResponse }>()
defineEmits<{ adjust: [text?: string] }>()
const result = computed(() => props.response.result)
const plan = computed(() => props.response.plan.plan)
const metric = computed(() =>
  'metric' in result.value ? researchMetricLabels[result.value.metric] : 'Datensätze',
)
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
  if (r.reason === 'duplicate_target') return 'Bitte verwende unterschiedliche Vergleichsziele.'
  return `Welche Zuordnung meinst du${r.query ? ` mit „${r.query}“` : ''}?`
})
const fieldLabels = {
  area_query: 'Gebiet',
  venue_query: 'Veranstaltungsort',
  organization_query: 'Organisation',
  category_queries: 'Kategorie',
  genre_queries: 'Genre',
  comparison_targets: 'Vergleichsziel',
}
</script>
<template>
  <section class="space-y-3" aria-label="Antwort">
    <div class="space-y-2 rounded-lg border border-slate-200 bg-slate-50/60 p-4">
      <h3 class="type-section-title">
        {{ result.kind === 'needs_clarification' ? 'Frage präzisieren' : 'Antwort' }}
      </h3>
      <template v-if="result.kind === 'count'">
        <p class="text-2xl font-semibold tabular-nums" data-testid="research-count">
          {{ number(result.value) }} {{ metric }}
        </p>
      </template>
      <p v-else-if="result.kind === 'aggregate'">
        {{ metric }} nach
        {{
          { venue: 'Veranstaltungsort', organization: 'Organisation', category: 'Kategorie' }[
            result.group_by
          ]
        }}
        · {{ result.items.length }} gelieferte Gruppen (höchstens 20)
      </p>
      <p v-else-if="result.kind === 'comparison'">Vergleich: {{ metric }}</p>
      <template v-else-if="result.kind === 'records'">
        <p v-if="plan.ordering !== 'none'">
          {{
            plan.ordering === 'earliest'
              ? 'Früheste gefundene Veranstaltungen'
              : 'Späteste gefundene Veranstaltungen'
          }}
          · {{ result.items.length }} angezeigt (höchstens {{ plan.limit }})
        </p>
        <p v-else-if="result.total !== null">
          {{ number(result.total) }} Ergebnisse insgesamt · {{ result.items.length }} angezeigt
        </p>
        <p v-else>Semantische Relevanzsuche · bis zu 20 Treffer</p>
        <p v-if="result.total === null && plan.ordering === 'none'" class="text-sm text-slate-600">
          {{ result.items.length }} angezeigte Treffer. Keine vollständige Zählung aller passenden
          Datensätze.
        </p>
      </template>
      <template v-else>
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
          {{ area ? `${area} · ` : '' }}{{ period
          }}<span v-if="response.execution.time_from">
            · ab {{ response.execution.time_from }} Uhr</span
          >
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
            <th scope="row" class="p-2 font-normal">{{ item.name }}</th>
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
    <div v-if="result.kind === 'records'" class="space-y-2">
      <EmptyState v-if="!result.items.length" message="Keine passenden Datensätze gefunden." />
      <ResearchResult
        v-for="item in result.items"
        :key="researchKey(item)"
        :item="item"
        :semantic="response.execution.semantic"
        :show-full-date="plan.ordering !== 'none'"
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
        <dd>{{ plan.metric === 'none' ? 'Keine' : researchMetricLabels[plan.metric] }}</dd>
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
