<script setup lang="ts">
import type { z } from '#shared/zod'
import type { summarySchema } from '#shared/contracts'
import { dateTime, checkStatusLabels } from '~/utils/presentation'
defineProps<{ status?: z.infer<typeof summarySchema>['check_status'] }>()
</script>
<template>
  <section
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
