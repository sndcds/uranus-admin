<script setup lang="ts">
import SectionHeader from '~/components/SectionHeader.vue'
import { computed } from 'vue'
import type { DashboardSummary } from '#shared/contracts'
import { qualityRules } from '~/utils/quality'
import { metric } from '~/utils/presentation'
const props = defineProps<{ data: DashboardSummary | null; limit?: number; compact?: boolean }>()
const rules = computed(() =>
  props.data
    ? [...new Set([...(props.data.quality.rules ?? []), ...Object.keys(qualityRules)])]
    : [],
)
const visibleRules = computed(() => {
  const ordered = props.compact
    ? [...rules.value].sort(
        (a, b) =>
          (props.data?.quality.rule_counts?.[b] ?? -1) -
          (props.data?.quality.rule_counts?.[a] ?? -1),
      )
    : rules.value
  return props.limit ? ordered.slice(0, props.limit) : ordered
})
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
  <section v-if="compact" class="operations-panel self-start" aria-label="Datenqualitätsübersicht">
    <header class="operations-panel-header">
      <h3 class="type-section-title">Datenqualität</h3>
    </header>
    <div class="space-y-3 p-3">
      <template v-if="data">
        <p class="text-sm font-semibold tabular-nums">{{ metric(data.quality.total) }} Befunde</p>
        <div class="flex flex-wrap gap-2">
          <StatusBadge :label="`${metric(data.quality.errors)} Fehler`" tone="error" />
          <StatusBadge :label="`${metric(data.quality.warnings)} Warnungen`" tone="warning" />
          <StatusBadge :label="`${metric(data.quality.info)} Hinweise`" />
        </div>
        <p v-if="data.quality.total" class="text-xs font-semibold text-slate-600">
          {{
            data.quality.rule_counts
              ? `Top ${visibleRules.length} Regeln nach Anzahl`
              : 'Regelübersicht'
          }}
        </p>
        <ul
          v-if="data.quality.total"
          class="divide-y divide-slate-200"
          aria-label="Qualitätsregeln"
        >
          <li v-for="rule in visibleRules" :key="rule">
            <NuxtLink
              :to="{
                path: '/findings',
                query: {
                  active_only: 'true',
                  geo_scope_id: data.geo_scope_id ?? undefined,
                  rule,
                  entity_type: qualityRules[rule]?.entityType,
                  mode: data.quality.mode,
                },
              }"
              class="flex min-h-11 items-center gap-2 py-2 text-sm hover:bg-slate-50"
            >
              <span class="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1 break-words"
                ><span class="block text-xs font-semibold">{{
                  qualityRules[rule]?.label ?? rule
                }}</span
                ><SeverityBadge v-if="qualityRules[rule]" :severity="qualityRules[rule]!.severity"
              /></span>
              <span class="shrink-0 text-xs font-semibold tabular-nums">{{
                metric(data.quality.rule_counts?.[rule])
              }}</span>
              <AppIcon name="arrow" :size="14" class="shrink-0 text-fuchsia-700" />
            </NuxtLink>
          </li>
        </ul>
        <EmptyState v-else compact message="Keine aktuellen Qualitätsbefunde." />
      </template>
      <p v-else class="operations-meta">Qualitätsbestand nicht verfügbar.</p>
      <div class="flex flex-wrap gap-x-3">
        <NuxtLink
          v-if="visibleRules.length < rules.length"
          to="/quality"
          class="action-link text-xs"
          >Alle Regeln anzeigen →</NuxtLink
        >
        <NuxtLink
          :to="{
            path: '/findings',
            query: {
              mode: data?.quality.mode ?? 'persisted',
              active_only: 'true',
              geo_scope_id: data?.geo_scope_id ?? undefined,
            },
          }"
          class="action-link text-xs"
          >Qualitätsbefunde öffnen →</NuxtLink
        >
      </div>
    </div>
  </section>
  <section v-else class="min-w-0 space-y-3" aria-label="Datenqualitätsübersicht">
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
                active_only: 'true',
                geo_scope_id: data?.geo_scope_id ?? undefined,
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
        :to="{
          path: '/findings',
          query: {
            mode: data?.quality.mode ?? 'persisted',
            active_only: 'true',
            geo_scope_id: data?.geo_scope_id ?? undefined,
          },
        }"
        class="rounded hover:underline"
        >Qualitätsbefunde öffnen →</NuxtLink
      >
    </div>
  </section>
</template>
