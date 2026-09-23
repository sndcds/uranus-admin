<script setup lang="ts">
import { ref } from 'vue'
import CompactFacts from '../../../app/components/CompactFacts.vue'
import TechnicalInfoBar from '../../../app/components/TechnicalInfoBar.vue'
import DenseTable from '../../../app/components/DenseTable.vue'
import RecordSection from '../../../app/components/RecordSection.vue'
import EmptyState from '../../../app/components/EmptyState.vue'
import StatusBadge from '../../../app/components/StatusBadge.vue'
import AppIcon from '../../../app/components/AppIcon.vue'
import PageHeader from '../../../app/components/PageHeader.vue'
import DataListShell from '../../../app/components/DataListShell.vue'
import EntityTimeline from '../../../app/components/EntityTimeline.vue'
const selected = ref('')
const rows = [
  {
    id: '1',
    title: 'Kulturnacht am Hafen',
    type: 'Veranstaltung',
    status: 'In Prüfung',
    date: '23.09.2026 · 10:00',
  },
  {
    id: '2',
    title: 'Kulturverein Nord',
    type: 'Organisation',
    status: 'Offen',
    date: '23.09.2026 · 09:30',
  },
  { id: '3', title: 'Hafenbühne', type: 'Ort', status: 'Erledigt', date: '22.09.2026 · 16:45' },
]
const columns = [
  { key: 'title', label: 'Titel', rowHeader: true },
  { key: 'type', label: 'Objektart' },
  { key: 'status', label: 'Status' },
  { key: 'date', label: 'Erstellt' },
] as const
</script>
<template>
  <main class="operations-page mx-auto max-w-6xl p-4 sm:p-5">
    <h1 class="sr-only">Kulturbytes Komponentenreview</h1>
    <PageHeader
      title="Operations Center"
      description="Design System v2.1 · Komponentenreview · synthetische Beispieldaten"
    >
      <template #actions
        ><a href="#worklist" class="button-primary"
          ><AppIcon name="list" :size="16" />Arbeitsliste ansehen</a
        ></template
      >
    </PageHeader>
    <div class="operations-grid">
      <RecordSection title="Benutzerinformationen" surface="panel">
        <template #icon><AppIcon name="users" :size="18" /></template>
        <template #actions
          ><a class="action-link" href="#technical-review">Technik ansehen</a></template
        >
        <CompactFacts
          :items="[
            { label: 'E-Mail', value: 'anna@example.invalid' },
            { label: 'Benutzername', value: 'anna.beispiel' },
            { label: 'Kontostatus', value: 'Nicht aktiv', tone: 'error' },
            { label: 'Teammitgliedschaften', value: 0, description: 'einschließlich Einladungen' },
          ]"
        />
      </RecordSection>
      <RecordSection title="Qualität & Arbeitsstand" surface="panel">
        <CompactFacts
          :items="[
            { label: 'Befunde', value: 3 },
            { label: 'Markierungen', value: 0 },
            { label: 'Geprüft', value: false },
            { label: 'Letzte Prüfung', value: null },
          ]"
        />
      </RecordSection>
    </div>
    <RecordSection
      id="worklist"
      title="Priorisierte Arbeitsliste"
      surface="plain"
      description="Dichte Tabelle mit Status und eindeutigen Zeilenaktionen."
    >
      <DenseTable
        caption="Beispiel-Arbeitsliste"
        :columns="columns"
        :rows="rows"
        :row-key="(row) => row.id"
      >
        <template #cell-status="{ row }"
          ><StatusBadge
            :label="row.status"
            :tone="row.status === 'Erledigt' ? 'success' : 'warning'"
        /></template>
        <template #actions="{ row }"
          ><button
            class="action-link"
            :aria-label="`Details: ${row.title}`"
            @click="selected = row.title"
          >
            Details <AppIcon name="arrow" :size="14" /></button
        ></template>
      </DenseTable>
      <p v-if="selected" role="status" class="operations-meta">Ausgewählt: {{ selected }}</p>
    </RecordSection>
    <div class="operations-grid">
      <RecordSection title="Verknüpfte Datensätze" surface="panel"
        ><EmptyState
          variant="compact"
          title="Keine Verknüpfungen"
          message="Auf dieser Seite sind keine belegten Verknüpfungen vorhanden."
      /></RecordSection>
      <RecordSection title="Bearbeitung" surface="subtle"
        ><p class="type-body">
          Zusammengehörige Informationen erhalten klare Grenzen. Eine Hauptaktion, ergänzende Links
          und lesbare Status bleiben unterscheidbar.
        </p></RecordSection
      >
    </div>
    <RecordSection title="Dichte Liste" surface="table">
      <DataListShell as="ul" dense aria-label="Dichte Beispiel-Liste" class="border-0">
        <li
          v-for="row in rows"
          :key="row.id"
          class="data-row flex flex-wrap items-center justify-between gap-x-3"
        >
          <span class="type-row-title min-w-0">{{ row.title }}</span>
          <button
            class="action-link"
            :aria-label="`Listendetails: ${row.title}`"
            @click="selected = row.title"
          >
            Details
          </button>
        </li>
      </DataListShell>
    </RecordSection>
    <EntityTimeline entity-type="user" entity-key="20000000-0000-4000-8000-000000000001" compact />
    <TechnicalInfoBar
      id="technical-review"
      :items="[
        {
          label: 'UUID',
          value: '20000000-0000-4000-8000-000000000001',
          mono: true,
          copyable: true,
        },
        { label: 'Datenstand des Abrufs', value: '23.09.2026 · 10:00', metadata: 'Europe/Berlin' },
        { label: 'Generation', value: 1 },
        { label: 'Prüfversuche', value: 0 },
      ]"
    />
    <details class="section-panel p-4">
      <summary class="min-h-11 cursor-pointer text-sm font-semibold">
        Tabellenalternative: lokal scrollen
      </summary>
      <DenseTable
        caption="Lokal scrollbare Beispiel-Tabelle"
        mobile="scroll"
        :columns="columns"
        :rows="rows"
        :row-key="(row) => row.id"
      />
    </details>
  </main>
</template>
