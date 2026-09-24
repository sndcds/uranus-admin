<script setup lang="ts">
import CompactFacts from '~/components/CompactFacts.vue'
import RecordSection from '~/components/RecordSection.vue'
import { computed } from 'vue'
import type { DashboardSummary } from '#shared/contracts'
import { qualityRuleLabel, qualityRules, qualityRuleDescriptions } from '~/utils/quality'
import { metric } from '~/utils/presentation'
const props = defineProps<{ data: DashboardSummary | null; limit?: number; compact?: boolean }>()
const rules = computed(() =>
  props.data
    ? [
        ...new Set([
          ...(props.data.quality.rules ?? []),
          ...Object.keys(qualityRules),
          ...(props.compact ? [] : ['venue_missing_geolocation']),
        ]),
      ]
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
    {
      title: 'Regeln',
      rules: visibleRules.value.filter(
        (rule) => !qualityRules[rule] && rule !== 'venue_missing_geolocation',
      ),
    },
    ...[...new Set(Object.values(qualityRules).map((rule) => rule.group))].map((title) => ({
      title,
      rules: visibleRules.value.filter(
        (rule) =>
          qualityRules[rule]?.group === title ||
          (title === 'Standorte' && rule === 'venue_missing_geolocation'),
      ),
    })),
  ].filter((group) => group.rules.length),
)
const summaryFacts = computed(() => [
  { label: 'Fehler', value: props.data?.quality.errors, tone: 'error' as const },
  { label: 'Warnungen', value: props.data?.quality.warnings, tone: 'warning' as const },
  { label: 'Hinweise', value: props.data?.quality.info, tone: 'info' as const },
  { label: 'Befunde', value: props.data?.quality.total },
])
function ruleLink(rule: string) {
  if (rule === 'venue_missing_geolocation')
    return '/findings?rule=venue_missing_geolocation&entity_type=venue&status=open'
  return {
    path: '/findings',
    query: {
      active_only: 'true',
      geo_scope_id: props.data?.geo_scope_id ?? undefined,
      rule,
      entity_type: qualityRules[rule]?.entityType,
      mode: props.data?.quality.mode,
    },
  }
}
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
                ><span class="block text-xs font-semibold">{{ qualityRuleLabel(rule) }}</span
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
  <section v-else class="min-w-0 space-y-4" aria-label="Datenqualitätsübersicht">
    <RecordSection v-if="data" title="Qualitätsstatus" surface="subtle" class="quality-summary">
      <CompactFacts :items="summaryFacts" :columns="4" />
      <EmptyState v-if="!data.quality.total" compact message="Keine aktuellen Qualitätsbefunde." />
    </RecordSection>
    <div class="quality-rule-groups min-w-0">
      <RecordSection
        v-for="group in groups"
        :key="group.title"
        :title="group.title"
        surface="table"
      >
        <ul
          class="divide-y divide-slate-200"
          :aria-label="group.title === 'Regeln' ? 'Qualitätsregeln' : group.title"
        >
          <li
            v-for="rule in group.rules"
            :key="rule"
            :data-quality-rule="rule"
            class="quality-rule p-3"
          >
            <div class="min-w-0 space-y-1">
              <div class="flex min-w-0 flex-wrap items-start justify-between gap-2">
                <h4 class="min-w-0 flex-1 break-words text-sm font-semibold">
                  {{ qualityRuleLabel(rule) }}
                </h4>
                <span class="text-sm font-semibold tabular-nums">{{
                  metric(data?.quality.rule_counts?.[rule])
                }}</span>
              </div>
              <p v-if="qualityRuleDescriptions[rule]" class="operations-meta">
                {{ qualityRuleDescriptions[rule] }}
              </p>
              <SeverityBadge
                v-if="qualityRules[rule] || rule === 'venue_missing_geolocation'"
                :severity="qualityRules[rule]?.severity ?? 'warning'"
              />
            </div>
            <NuxtLink
              :to="ruleLink(rule)"
              class="button button-compact justify-self-end"
              :aria-label="`Befunde öffnen: ${qualityRuleLabel(rule)}`"
              >Befunde öffnen</NuxtLink
            >
          </li>
        </ul>
      </RecordSection>
    </div>
    <div class="flex flex-wrap gap-3">
      <NuxtLink v-if="visibleRules.length < rules.length" to="/quality" class="action-link text-xs"
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
        class="button button-compact"
        >Qualitätsbefunde öffnen</NuxtLink
      >
    </div>
  </section>
</template>

<style scoped>
.quality-summary :deep(dl) {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.quality-rule-groups > section {
  break-inside: avoid;
  margin-bottom: 0.75rem;
}
.quality-rule {
  display: grid;
  gap: 0.5rem 0.75rem;
  align-items: center;
}
@media (min-width: 640px) {
  .quality-rule {
    grid-template-columns: minmax(0, 1fr) auto;
  }
}
@media (min-width: 1280px) {
  .quality-summary :deep(dl) {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
  .quality-rule-groups {
    columns: 2;
    column-gap: 0.75rem;
  }
}
</style>
