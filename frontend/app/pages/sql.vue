<script setup lang="ts">
import { computed, ref } from 'vue'
import SqlWorkspace from '~/components/sql/SqlWorkspace.vue'
import SqlConsolePanel from '~/components/sql/SqlConsolePanel.vue'
import type { TechnicalFact } from '~/utils/operations'
const connected = ref(false)
const initialSql = 'SELECT\n    *\nFROM uranus.event\nLIMIT 50;'
const technicalItems = computed<TechnicalFact[]>(() => [
  { label: 'Datasource', value: 'Uranus' },
  { label: 'Mode', value: 'READ ONLY' },
  { label: 'Scope', value: 'uranus.*', mono: true },
  { label: 'Connection', value: connected.value ? 'verbunden' : 'getrennt' },
  { label: 'Query timeout', value: '5s' },
  { label: 'Row limit', value: 500 },
  { label: 'Gesamtdeadline', value: '8s' },
])
</script>
<template>
  <section class="operations-page" aria-labelledby="sql-title">
    <PageHeader
      title="SQL Console"
      title-id="sql-title"
      description="Uranus read-only untersuchen und SQL-Abfragen kontrolliert ausführen."
    />
    <div class="operations-workspace">
      <SqlWorkspace page>
        <template #context>
          <h3 class="text-sm font-semibold">Datenbankkontext</h3>
          <div class="mt-3 flex flex-wrap items-center gap-2">
            <AppIcon name="database" :size="18" />
            <strong class="text-sm">Uranus</strong>
            <StatusBadge label="READ ONLY" />
          </div>
          <dl class="sql-context-facts mt-3 text-xs">
            <div>
              <dt class="operations-meta">Scope</dt>
              <dd class="font-mono">uranus.*</dd>
            </div>
            <div>
              <dt class="operations-meta">Connection</dt>
              <dd role="status" aria-live="polite">
                <StatusBadge
                  :label="connected ? 'verbunden' : 'getrennt'"
                  :tone="connected ? 'success' : 'neutral'"
                />
              </dd>
            </div>
            <div>
              <dt class="operations-meta">Limits</dt>
              <dd>5s · 500 Zeilen</dd>
              <dd>8s Gesamtdeadline</dd>
            </div>
          </dl>
        </template>
        <SqlConsolePanel :sql="initialSql" page @connection="connected = $event" />
      </SqlWorkspace>
      <footer class="operations-workspace-footer overflow-hidden rounded-b-xl">
        <TechnicalInfoBar :items="technicalItems" :show-title="false" />
      </footer>
    </div>
  </section>
</template>
<style scoped>
.sql-context-facts {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1.5rem;
}
@media (min-width: 1280px) {
  .sql-context-facts {
    flex-direction: column;
  }
}
</style>
