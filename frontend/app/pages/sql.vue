<script setup lang="ts">
import { ref } from 'vue'
import SqlWorkspace from '~/components/sql/SqlWorkspace.vue'
import SqlConsolePanel from '~/components/sql/SqlConsolePanel.vue'
const connected = ref(false)
const initialSql =
  'SELECT\n    uuid,\n    event_uuid,\n    start_date,\n    start_time,\n    end_date,\n    end_time\nFROM uranus_console.event_date\nLIMIT 50;'
</script>
<template>
  <div class="space-y-5">
    <PageHeader
      title="SQL Console"
      description="Interaktive Abfragen auf freigegebenen Uranus-Daten."
    />
    <section class="card overflow-hidden">
      <SqlWorkspace>
        <template #context>
          <h2 class="font-semibold">SQL Console</h2>
          <dl class="mt-4 space-y-4 text-xs">
            <div>
              <dt class="text-slate-500">Datasource</dt>
              <dd>Uranus Console</dd>
            </div>
            <div>
              <dt class="text-slate-500">Mode</dt>
              <dd>READ ONLY</dd>
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
