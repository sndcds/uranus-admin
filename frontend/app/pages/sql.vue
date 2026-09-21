<script setup lang="ts">
import { ref } from 'vue'
import SqlWorkspace from '~/components/sql/SqlWorkspace.vue'
import SqlConsolePanel from '~/components/sql/SqlConsolePanel.vue'
const connected = ref(false)
const initialSql = 'SELECT\n    *\nFROM uranus.event\nLIMIT 50;'
</script>
<template>
  <div class="space-y-5">
    <PageHeader
      title="SQL Console"
      description="Systemadministratoren können alle Tabellen und Spalten des Uranus-Schemas lesen."
    />
    <section class="card overflow-hidden">
      <SqlWorkspace>
        <template #context>
          <h2 class="font-semibold">SQL Console</h2>
          <dl class="mt-4 space-y-4 text-xs">
            <div>
              <dt class="text-slate-500">Datasource</dt>
              <dd>Uranus</dd>
            </div>
            <div>
              <dt class="text-slate-500">Mode</dt>
              <dd>READ ONLY</dd>
            </div>
            <div>
              <dt class="text-slate-500">Scope</dt>
              <dd>uranus.*</dd>
            </div>
            <div>
              <dt class="text-slate-500">Connection</dt>
              <dd aria-live="polite">{{ connected ? 'verbunden' : 'getrennt' }}</dd>
            </div>
            <div>
              <dt class="text-slate-500">Limits</dt>
              <dd>5s / 500 rows</dd>
              <dd>8s Gesamtdeadline</dd>
            </div>
          </dl>
        </template>
        <SqlConsolePanel :sql="initialSql" page @connection="connected = $event" />
      </SqlWorkspace>
    </section>
  </div>
</template>
