<script setup lang="ts">
import { dateTime, findingStatusLabels } from '~/utils/presentation'
import type { Finding } from '#shared/contracts'
defineProps<{ items: Finding[] }>()
const detail = useTemplateRef('detail')
</script>

<template>
  <ul class="divide-y divide-slate-100" aria-label="Befunde">
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
            class="rounded font-semibold text-fuchsia-700 hover:underline"
            :aria-label="`Befund zu ${finding.entity_name} ansehen`"
            @click="detail?.open(finding)"
          >
            Ansehen
          </button>
          <NuxtLink
            v-if="finding.action"
            :to="finding.action.href"
            class="rounded text-fuchsia-700 hover:underline"
            >Im Admin ansehen</NuxtLink
          >
          <RecordMarkLink :entity-type="finding.entity_type" :entity-key="finding.entity_key" />
        </div>
      </div>
    </li>
  </ul>
  <FindingDetail ref="detail" />
</template>
