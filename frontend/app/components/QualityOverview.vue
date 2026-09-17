<script setup lang="ts">
import SectionHeader from '~/components/SectionHeader.vue'
import { computed } from 'vue'
import type { DashboardSummary } from '#shared/contracts'
import { qualityRules } from '~/utils/quality'
import { metric } from '~/utils/presentation'
const props = defineProps<{ data: DashboardSummary | null; limit?: number }>()
const rules = computed(() =>
  props.data
    ? [...new Set([...(props.data.quality.rules ?? []), ...Object.keys(qualityRules)])]
    : [],
)
const visibleRules = computed(() => (props.limit ? rules.value.slice(0, props.limit) : rules.value))
const groups = computed(() =>
  [
    { title: 'Regeln', rules: visibleRules.value.filter((rule) => !qualityRules[rule]) },
    ...[...new Set(Object.values(qualityRules).map((rule) => rule.group))].map((title) => ({
      title,
      rules: visibleRules.value.filter((rule) => qualityRules[rule]?.group === title),
    })),
  ].filter((group) => group.rules.length),
)
</script>

<template>
  <section class="min-w-0 space-y-3" aria-label="Datenqualitätsübersicht">
    <SectionHeader v-if="limit" title="Datenqualität" />
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
    <DataListShell v-for="group in groups" :key="group.title">
      <div class="list-group-header">
        <h3 class="text-xs font-semibold">{{ group.title }}</h3>
      </div>
      <ul
        class="divide-y divide-slate-100"
        :aria-label="group.title === 'Regeln' ? 'Qualitätsregeln' : group.title"
      >
        <li v-for="rule in group.rules" :key="rule">
          <NuxtLink
            :to="{
              path: '/findings',
              query: {
                rule,
                entity_type: qualityRules[rule]?.entityType,
                mode: data?.quality.mode,
              },
            }"
            class="data-row flex items-center justify-between gap-3 text-sm font-semibold text-slate-700 hover:text-fuchsia-700"
          >
            <span class="min-w-0 space-y-1">
              <span class="block break-words">{{ qualityRules[rule]?.label ?? rule }}</span>
              <span v-if="qualityRules[rule]" class="flex flex-wrap items-center gap-2">
                <SeverityBadge :severity="qualityRules[rule]!.severity" />
                <span
                  v-if="qualityRules[rule]!.severity === 'warning'"
                  class="text-xs font-normal text-slate-500"
                  >Schlechte Datenqualität</span
                >
              </span>
            </span>
            <span class="ml-auto shrink-0 tabular-nums">{{
              metric(data?.quality.rule_counts?.[rule])
            }}</span>
            <AppIcon name="arrow" :size="14" class="shrink-0 text-fuchsia-700" />
          </NuxtLink>
        </li>
      </ul>
    </DataListShell>
    <EmptyState v-if="data && !data.quality.total" message="Keine aktuellen Qualitätsbefunde." />
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
