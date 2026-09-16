<script setup lang="ts">
import { computed } from 'vue'
import type { DashboardSummary } from '#shared/contracts'
const props = defineProps<{ data: DashboardSummary | null; limit?: number }>()
const rules = computed(() => props.data?.quality.rules ?? [])
const visibleRules = computed(() => (props.limit ? rules.value.slice(0, props.limit) : rules.value))
</script>

<template>
  <section class="min-w-0 space-y-3" aria-label="Datenqualitätsübersicht">
    <h2 v-if="limit" class="text-base font-semibold">Datenqualität</h2>
    <ResultSummary
      v-if="data"
      :total="data.quality.total"
      noun="Befunde"
      label="Qualitätsbestand"
      :description="
        data.quality.mode === 'live'
          ? 'Live-Diagnose'
          : 'Gespeicherter Bestand ohne behobene Befunde'
      "
    >
      <StatusBadge :label="`${data.quality.errors} Fehler`" tone="error" />
      <StatusBadge :label="`${data.quality.warnings} Warnungen`" tone="warning" />
      <StatusBadge :label="`${data.quality.info} Hinweise`" />
    </ResultSummary>
    <DataListShell v-if="visibleRules.length">
      <div class="list-group-header">
        <h3 class="text-xs font-semibold">Regeln</h3>
        <span class="text-xs text-slate-500">{{ visibleRules.length }} von {{ rules.length }}</span>
      </div>
      <ul class="divide-y divide-slate-100" aria-label="Qualitätsregeln">
        <li v-for="rule in visibleRules" :key="rule">
          <NuxtLink
            :to="{ path: '/findings', query: { rule, mode: data?.quality.mode } }"
            class="data-row flex items-center justify-between gap-3 text-sm font-semibold text-slate-700 hover:text-fuchsia-700"
          >
            <span class="min-w-0 break-words">{{ rule }}</span>
            <AppIcon name="arrow" :size="14" class="shrink-0 text-fuchsia-700" />
          </NuxtLink>
        </li>
      </ul>
    </DataListShell>
    <EmptyState v-else-if="data" message="Keine Regeln in dieser Übersicht verfügbar." />
    <div class="flex flex-wrap gap-4 text-sm font-semibold text-fuchsia-700">
      <NuxtLink
        v-if="visibleRules.length < rules.length"
        to="/quality"
        class="rounded hover:underline"
        >Alle Regeln anzeigen →</NuxtLink
      >
      <NuxtLink
        :to="{ path: '/findings', query: { mode: data?.quality.mode ?? 'persisted' } }"
        class="rounded hover:underline"
        >Qualitätsbefunde öffnen →</NuxtLink
      >
    </div>
  </section>
</template>
