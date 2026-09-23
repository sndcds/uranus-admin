<script setup lang="ts">
import type { z } from '#shared/zod'
import type { summarySchema } from '#shared/contracts'
import { dateTime, checkStatusLabels } from '~/utils/presentation'
import KpiCard from './KpiCard.vue'
defineProps<{ status?: z.infer<typeof summarySchema>['check_status']; compact?: boolean }>()
</script>
<template>
  <KpiCard
    v-if="compact"
    compact
    label="Prüfstatus"
    :description="
      status?.latest_run
        ? `${status.latest_run.rule_count} Regeln · ${status.latest_run.finding_count} Befunde`
        : status
          ? 'Noch kein Lauf vorhanden.'
          : 'Keine Prüflaufdaten verfügbar.'
    "
    to="/checks"
    action-label="Prüfläufe öffnen"
  >
    <template #value>
      <StatusBadge
        v-if="status?.latest_run"
        :label="checkStatusLabels[status.latest_run.status]"
        :tone="
          status.latest_run.status === 'failed'
            ? 'error'
            : status.latest_run.status === 'success'
              ? 'success'
              : 'neutral'
        "
      />
      <span v-else class="text-sm text-slate-600">{{
        status ? 'Noch keine Prüfläufe' : 'Nicht verfügbar'
      }}</span>
    </template>
    <template #meta>
      <p v-if="status?.latest_run" class="text-xs leading-4 text-slate-600">
        Letzter Lauf:
        <time :datetime="status.latest_run.started_at" title="Europe/Berlin">{{
          dateTime(status.latest_run.started_at)
        }}</time>
      </p>
    </template>
  </KpiCard>
  <section
    v-else
    class="space-y-2 rounded-2xl border border-slate-200 bg-white p-4"
    aria-label="Prüfstatus"
  >
    <h3 class="text-sm font-semibold">Prüfstatus</h3>
    <template v-if="status?.latest_run">
      <StatusBadge
        :label="checkStatusLabels[status.latest_run.status]"
        :tone="
          status.latest_run.status === 'failed'
            ? 'error'
            : status.latest_run.status === 'success'
              ? 'success'
              : 'neutral'
        "
      />
      <p class="text-xs text-slate-500">
        Letzter Lauf: {{ dateTime(status.latest_run.started_at) }}
      </p>
      <p class="text-xs text-slate-500">
        {{ status.latest_run.rule_count }} Regeln · {{ status.latest_run.finding_count }} Befunde
      </p>
    </template>
    <p v-else class="text-sm text-slate-500">
      {{ status ? 'Noch keine Prüfläufe' : 'Nicht verfügbar' }}
    </p>
    <p v-if="status?.last_successful_run" class="text-xs text-slate-500">
      Letzter erfolgreicher Lauf: {{ dateTime(status.last_successful_run.finished_at) }}
    </p>
    <p v-else-if="status?.latest_run" class="text-xs text-slate-500">
      Noch kein erfolgreicher Lauf
    </p>
    <NuxtLink to="/checks" class="inline-block text-sm font-semibold text-fuchsia-700"
      >Prüfläufe öffnen</NuxtLink
    >
  </section>
</template>
