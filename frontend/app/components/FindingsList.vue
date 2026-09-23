<script setup lang="ts">
import { dateTime, findingStatusLabels } from '~/utils/presentation'
import type { Finding } from '#shared/contracts'
import SqlEditorModal from './sql/SqlEditorModal.vue'
defineProps<{ items: Finding[]; compact?: boolean }>()
const detail = useTemplateRef('detail')
const sqlEditor = useTemplateRef('sqlEditor')
</script>

<template>
  <table v-if="compact" class="operations-table operations-table-stack" role="table">
    <caption class="sr-only">
      Priorisierte Befunde
    </caption>
    <colgroup>
      <col class="w-[36%]" />
      <col class="w-[18%]" />
      <col class="w-[30%]" />
      <col class="w-[16%]" />
    </colgroup>
    <thead role="rowgroup">
      <tr role="row">
        <th scope="col" role="columnheader">Titel / Priorität</th>
        <th scope="col" role="columnheader">Typ / Status</th>
        <th scope="col" role="columnheader">Quelle / Beobachtet</th>
        <th scope="col" role="columnheader">Aktionen</th>
      </tr>
    </thead>
    <tbody role="rowgroup">
      <tr v-for="finding in items" :key="finding.id" role="row">
        <th scope="row" role="rowheader" class="max-sm:block">
          <span class="operations-cell-label max-sm:hidden" aria-hidden="true"
            >Titel / Priorität</span
          >
          <div class="min-w-0 py-1">
            <div class="flex flex-wrap items-baseline gap-x-2">
              <span
                class="text-xs font-semibold text-slate-600"
                :aria-label="`Priorität ${finding.priority}`"
                >P{{ finding.priority }}</span
              >
              <h4 class="text-sm font-semibold">{{ finding.entity_name }}</h4>
            </div>
            <p class="mt-1 text-xs font-normal leading-4 text-slate-600">{{ finding.message }}</p>
          </div>
        </th>
        <td role="cell">
          <span class="operations-cell-label" aria-hidden="true">Typ / Status</span>
          <div class="flex flex-wrap gap-1 py-1">
            <SeverityBadge :severity="finding.severity" />
            <EntityTypeBadge :type="finding.entity_type" />
            <StatusBadge
              v-if="finding.status"
              :label="findingStatusLabels[finding.status] ?? finding.status"
            />
          </div>
        </td>
        <td role="cell">
          <span class="operations-cell-label" aria-hidden="true">Quelle / Beobachtet</span>
          <div class="space-y-1 py-1 text-xs text-slate-600">
            <p>{{ finding.organization_name || 'Keine eindeutige Organisation' }}</p>
            <p>Feld: {{ finding.field }}</p>
            <time :datetime="finding.last_seen_at" title="Europe/Berlin">{{
              dateTime(finding.last_seen_at)
            }}</time>
          </div>
        </td>
        <td role="cell">
          <span class="operations-cell-label" aria-hidden="true">Aktionen</span>
          <div class="flex flex-wrap items-center">
            <button
              class="action-link min-w-11 justify-center"
              :aria-label="`Befund zu ${finding.entity_name} ansehen`"
              @click="detail?.open(finding)"
            >
              <AppIcon name="arrow" :size="16" />
            </button>
            <details class="relative">
              <summary
                class="flex min-h-11 min-w-11 cursor-pointer list-none items-center justify-center rounded text-slate-600 hover:bg-slate-100"
                :aria-label="`Weitere Aktionen für ${finding.entity_name}`"
              >
                <AppIcon name="menu" :size="16" />
              </summary>
              <div class="operations-panel absolute right-0 z-10 w-56 p-2 shadow-lg">
                <button
                  v-if="finding.sql_diagnostic_available"
                  class="action-link w-full text-xs"
                  :aria-label="`SQL Editor für ${finding.entity_name}`"
                  @click="sqlEditor?.open(finding)"
                >
                  SQL Editor <AppIcon name="arrow" :size="14" />
                </button>
                <NuxtLink
                  v-if="finding.action"
                  :to="finding.action.href"
                  class="action-link w-full text-xs"
                  >Im Admin ansehen</NuxtLink
                >
                <NuxtLink
                  v-if="finding.location_suggestion_request_id"
                  :to="`/geocoding/${finding.location_suggestion_request_id}`"
                  class="action-link w-full text-xs"
                  >Standortvorschlag prüfen</NuxtLink
                >
                <div
                  class="[&_a]:m-0 [&_a]:w-full [&_a]:justify-start [&_a]:border-0 [&_a]:px-0 [&_a]:text-xs"
                >
                  <RecordMarkLink
                    :entity-type="finding.entity_type"
                    :entity-key="finding.entity_key"
                  />
                </div>
              </div>
            </details>
          </div>
        </td>
      </tr>
    </tbody>
  </table>
  <ul v-else class="divide-y divide-slate-100" aria-label="Befunde">
    <li
      v-for="finding in items"
      :key="finding.id"
      class="data-row grid gap-3 md:grid-cols-[auto_minmax(0,1fr)]"
    >
      <span
        aria-hidden="true"
        class="mt-1 hidden h-3 w-3 rounded-full md:block"
        :class="
          finding.severity === 'error'
            ? 'bg-rose-500'
            : finding.severity === 'warning'
              ? 'bg-amber-400'
              : 'bg-sky-400'
        "
      />
      <div class="min-w-0 lg:grid lg:grid-cols-[minmax(0,1fr)_auto] lg:gap-x-4">
        <div class="flex flex-wrap items-center gap-2">
          <h3 class="break-words text-sm font-semibold">{{ finding.entity_name }}</h3>
          <SeverityBadge :severity="finding.severity" /><EntityTypeBadge
            :type="finding.entity_type"
          />
          <StatusBadge
            v-if="finding.status"
            :label="findingStatusLabels[finding.status] ?? finding.status"
          />
        </div>
        <p class="mt-1 break-words text-sm text-slate-600 lg:col-start-1">{{ finding.message }}</p>
        <p class="mt-1 text-xs text-slate-500 lg:col-start-1">
          Feld: {{ finding.field }} ·
          {{ finding.organization_name || 'Keine eindeutige Organisation' }} · beobachtet
          {{ dateTime(finding.last_seen_at) }}
        </p>
        <div
          class="mt-2 flex flex-wrap items-center lg:col-start-2 lg:row-span-3 lg:row-start-1 lg:mt-0 lg:max-w-40 lg:justify-end gap-x-4 gap-y-2 text-xs [&_a]:mt-0 [&_a]:p-0 [&_a]:border-0 [&_a]:text-xs"
        >
          <button
            v-if="finding.sql_diagnostic_available"
            class="inline-flex items-center gap-1 rounded font-semibold text-fuchsia-700 hover:underline"
            :aria-label="`SQL Editor für ${finding.entity_name}`"
            @click="sqlEditor?.open(finding)"
          >
            SQL Editor <AppIcon name="arrow" :size="14" />
          </button>
          <button
            class="rounded hover:underline"
            :class="
              finding.sql_diagnostic_available ? 'text-slate-500' : 'font-semibold text-fuchsia-700'
            "
            :aria-label="`Befund zu ${finding.entity_name} ansehen`"
            @click="detail?.open(finding)"
          >
            {{ finding.sql_diagnostic_available ? 'Details' : 'Ansehen' }}
          </button>
          <NuxtLink
            v-if="finding.action"
            :to="finding.action.href"
            class="rounded text-fuchsia-700 hover:underline"
            >Im Admin ansehen</NuxtLink
          >
          <NuxtLink
            v-if="finding.location_suggestion_request_id"
            :to="`/geocoding/${finding.location_suggestion_request_id}`"
            class="text-fuchsia-700 hover:underline"
            >Standortvorschlag prüfen</NuxtLink
          >
          <RecordMarkLink :entity-type="finding.entity_type" :entity-key="finding.entity_key" />
        </div>
      </div>
    </li>
  </ul>
  <FindingDetail ref="detail" />
  <SqlEditorModal ref="sqlEditor" />
</template>
