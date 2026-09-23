<script setup lang="ts">
import { qualityRuleLabel } from '~/utils/quality'
import { dateTime, findingStatusLabels } from '~/utils/presentation'
import {
  findingAdditionalMessage,
  findingRecordKey,
  findingRecordName,
} from '~/utils/finding-presentation'
import type { Finding } from '#shared/contracts'
import SqlEditorModal from './sql/SqlEditorModal.vue'
import FindingDetail from './FindingDetail.vue'
withDefaults(
  defineProps<{
    items: Finding[]
    compact?: boolean
    workspace?: boolean
    mode?: 'persisted' | 'live'
  }>(),
  { mode: 'persisted' },
)
const emit = defineEmits<{ refresh: [] }>()
const sqlEditor = useTemplateRef('sqlEditor')
const detail = useTemplateRef('detail')
</script>

<template>
  <div
    v-if="compact"
    :class="workspace ? 'findings-scroll' : undefined"
    :tabindex="workspace ? 0 : undefined"
    :aria-label="workspace ? 'Priorisierte Arbeitsliste scrollen' : undefined"
    :role="workspace ? 'region' : undefined"
  >
    <table
      class="operations-table findings-table"
      :class="{ 'findings-workspace': workspace }"
      role="table"
    >
      <caption class="sr-only">
        Priorisierte Befunde
      </caption>
      <colgroup>
        <col v-if="workspace" class="w-[7%]" />
        <col :class="workspace ? 'w-[27%]' : 'w-[31%]'" />
        <col class="w-[32%]" />
        <col :class="workspace ? 'w-[15%]' : 'w-[17%]'" />
        <col :class="workspace ? 'w-[19%]' : 'w-[20%]'" />
      </colgroup>
      <thead role="rowgroup">
        <tr role="row">
          <th v-if="workspace" scope="col" role="columnheader">Prio</th>
          <th scope="col" role="columnheader">Datensatz</th>
          <th scope="col" role="columnheader">Befund</th>
          <th scope="col" role="columnheader">{{ workspace ? 'Status' : 'Priorität / Status' }}</th>
          <th scope="col" role="columnheader">Aktionen</th>
        </tr>
      </thead>
      <tbody role="rowgroup">
        <tr v-for="finding in items" :key="finding.id" role="row">
          <td v-if="workspace" role="cell" class="findings-priority">
            <span
              class="inline-flex rounded bg-slate-900 px-2 py-1 text-xs font-semibold text-white"
              :aria-label="`Priorität ${finding.priority}`"
              >P{{ finding.priority }}</span
            >
          </td>
          <th scope="row" role="rowheader" class="findings-record">
            <div class="flex min-w-0 items-start gap-3 py-2">
              <ActivityThumbnail :item="finding" compact />
              <div class="min-w-0 space-y-1">
                <component :is="workspace ? 'h3' : 'h4'" class="text-sm font-semibold leading-5">
                  {{ findingRecordName(finding) }}
                </component>
                <p v-if="findingRecordKey(finding)" class="text-xs font-normal text-slate-500">
                  <span :title="finding.entity_key">{{ findingRecordKey(finding) }}</span>
                </p>
                <EntityTypeBadge :type="finding.entity_type" />
                <p
                  v-if="finding.organization_name"
                  class="text-xs font-normal leading-4 text-slate-500"
                >
                  {{ finding.organization_name }}
                </p>
              </div>
            </div>
          </th>
          <td role="cell" class="findings-evidence">
            <div class="space-y-1 py-2">
              <p class="text-sm font-medium leading-5 text-slate-900">
                {{ qualityRuleLabel(finding.rule) }}
              </p>
              <p v-if="findingAdditionalMessage(finding)" class="text-xs leading-4 text-slate-600">
                {{ findingAdditionalMessage(finding) }}
              </p>
              <p class="pt-1 text-xs leading-4 text-slate-500">
                Feld: {{ finding.field }}
                <span class="block"
                  >Beobachtet:
                  <time :datetime="finding.last_seen_at" title="Europe/Berlin">{{
                    dateTime(finding.last_seen_at)
                  }}</time>
                </span>
              </p>
            </div>
          </td>
          <td role="cell" class="findings-status">
            <div class="space-y-2 py-2">
              <StatusBadge
                v-if="finding.status && (!workspace || mode === 'persisted')"
                :label="findingStatusLabels[finding.status] ?? finding.status"
              />
              <StatusBadge v-if="workspace && mode === 'live'" label="Live-Diagnose" />
              <div class="flex flex-wrap items-center gap-2">
                <span
                  v-if="!workspace"
                  class="rounded bg-slate-900 px-1.5 py-0.5 text-xs font-semibold text-white"
                  :aria-label="`Priorität ${finding.priority}`"
                  >P{{ finding.priority }}</span
                >
                <SeverityBadge :severity="finding.severity" />
              </div>
            </div>
          </td>
          <td role="cell" class="findings-actions">
            <div
              class="flex flex-col items-start"
              :class="workspace ? 'findings-row-actions' : 'sm:[&_.action-link]:min-h-6'"
            >
              <button
                v-if="workspace"
                class="button findings-edit"
                :aria-label="`Befund bearbeiten: ${findingRecordName(finding)}`"
                @click="detail?.open(finding, mode)"
              >
                Befund bearbeiten
              </button>
              <NuxtLink
                v-if="finding.action && !workspace"
                :to="finding.action.href"
                class="action-link text-xs"
                >Im Admin ansehen</NuxtLink
              >
              <button
                v-if="finding.sql_diagnostic_available"
                class="action-link text-xs"
                :aria-label="`SQL Editor für ${findingRecordName(finding)}`"
                @click="sqlEditor?.open(finding, mode)"
              >
                SQL Editor
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <ul v-else class="divide-y divide-slate-100" aria-label="Befunde">
    <li
      v-for="finding in items"
      :key="finding.id"
      class="data-row grid grid-cols-[auto_minmax(0,1fr)] gap-3"
    >
      <ActivityThumbnail :item="finding" compact />
      <div class="min-w-0 lg:grid lg:grid-cols-[minmax(0,1fr)_auto] lg:gap-x-4">
        <div class="flex flex-wrap items-center gap-2">
          <h3 class="break-words text-sm font-semibold">{{ findingRecordName(finding) }}</h3>
          <SeverityBadge :severity="finding.severity" /><EntityTypeBadge
            :type="finding.entity_type"
          />
          <StatusBadge
            v-if="finding.status"
            :label="findingStatusLabels[finding.status] ?? finding.status"
          />
        </div>
        <p
          v-if="findingRecordKey(finding)"
          class="text-xs text-slate-500"
          :title="finding.entity_key"
        >
          {{ findingRecordKey(finding) }}
        </p>
        <p v-if="finding.organization_name" class="mt-1 text-xs text-slate-500 lg:col-start-1">
          {{ finding.organization_name }}
        </p>
        <p class="mt-2 text-sm font-medium lg:col-start-1">{{ qualityRuleLabel(finding.rule) }}</p>
        <p
          v-if="findingAdditionalMessage(finding)"
          class="mt-1 text-xs text-slate-600 lg:col-start-1"
        >
          {{ findingAdditionalMessage(finding) }}
        </p>
        <p class="mt-1 text-xs text-slate-500 lg:col-start-1">
          Feld: {{ finding.field }} · beobachtet
          <time :datetime="finding.last_seen_at">{{ dateTime(finding.last_seen_at) }}</time>
        </p>
        <div
          class="mt-2 flex flex-col items-start sm:[&_.action-link]:min-h-6 lg:col-start-2 lg:row-span-6 lg:row-start-1 lg:mt-0"
        >
          <NuxtLink v-if="finding.action" :to="finding.action.href" class="action-link text-xs"
            >Im Admin ansehen</NuxtLink
          >
          <button
            v-if="finding.sql_diagnostic_available"
            class="action-link text-xs"
            :aria-label="`SQL Editor für ${findingRecordName(finding)}`"
            @click="sqlEditor?.open(finding, mode)"
          >
            SQL Editor
          </button>
        </div>
      </div>
    </li>
  </ul>
  <FindingDetail
    v-if="workspace"
    ref="detail"
    @refresh="emit('refresh')"
    @sql="(finding, source) => sqlEditor?.open(finding, source)"
  />
  <SqlEditorModal ref="sqlEditor" />
</template>

<style scoped>
.findings-workspace tbody :is(th, td) {
  border-color: var(--color-slate-200);
}
.findings-workspace tbody tr:focus-within {
  background: var(--color-slate-50);
  box-shadow: inset 3px 0 var(--color-fuchsia-600);
}
.findings-workspace .findings-priority {
  padding-top: 1rem;
}
.findings-workspace .findings-row-actions > * {
  min-height: 44px;
}
.findings-edit {
  padding-inline: 0.5rem;
  font-size: 0.75rem;
  text-align: left;
  color: var(--color-fuchsia-800);
  border-color: var(--color-fuchsia-200);
  background: var(--color-fuchsia-50);
}
@media (min-width: 1101px) {
  /* The scrollport owns its sticky header; no offset from the wrapping app header is needed. */
  .findings-scroll {
    max-height: 68dvh;
    overflow-y: auto;
  }
  .findings-workspace {
    border-collapse: separate;
    border-spacing: 0;
  }
  .findings-workspace thead {
    position: sticky;
    top: 0;
    z-index: 1;
  }
  .findings-workspace thead th {
    background: var(--color-slate-100);
    color: var(--color-slate-800);
    border-bottom: 1px solid var(--color-slate-300);
    padding-block: 0.75rem;
  }
}

.findings-table tbody :is(th, td) {
  vertical-align: top;
}
@media (max-width: 1100px) {
  .findings-table,
  .findings-table tbody {
    display: block;
    width: 100%;
  }
  .findings-table colgroup {
    display: none;
  }
  .findings-table thead {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }
  .findings-table tbody tr {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 11rem;
    height: auto;
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--color-slate-200);
  }
  .findings-table tbody :is(th, td) {
    min-width: 0;
    border: 0;
  }
  .findings-workspace tbody tr {
    grid-template-columns: 3.5rem minmax(0, 1fr) 10rem;
  }
  .findings-workspace .findings-priority {
    grid-column: 1;
    grid-row: 1 / span 2;
  }
  .findings-workspace .findings-record {
    grid-column: 2;
  }
  .findings-workspace .findings-evidence {
    grid-column: 2;
  }
  .findings-workspace .findings-status,
  .findings-workspace .findings-actions {
    grid-column: 3;
  }
  .findings-record {
    grid-column: 1;
    grid-row: 1;
  }
  .findings-evidence {
    grid-column: 1;
    grid-row: 2;
  }
  .findings-status {
    grid-column: 2;
    grid-row: 1;
  }
  .findings-actions {
    grid-column: 2;
    grid-row: 2;
  }
}
@media (max-width: 639px) {
  .findings-table tbody tr {
    grid-template-columns: minmax(0, 1fr);
  }
  .findings-table tbody :is(th, td) {
    grid-column: 1;
    grid-row: auto;
  }
  .findings-workspace tbody tr {
    grid-template-columns: minmax(0, 1fr);
  }
  .findings-workspace tbody :is(th, td) {
    grid-column: 1;
    grid-row: auto;
  }
  .findings-priority {
    order: 0;
  }
  .findings-workspace .findings-priority {
    padding-top: 0.25rem;
  }
  .findings-record {
    order: 1;
  }
  .findings-status {
    order: 2;
  }
  .findings-evidence {
    order: 3;
  }
  .findings-actions {
    order: 4;
  }
  .findings-status > div > * {
    margin-block: 0;
  }
  .findings-status > div {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem;
  }
}
</style>
