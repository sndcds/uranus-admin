<script setup lang="ts">
const store = useDashboardStore()
const { $adminApi } = useNuxtApp()
onMounted(() => {
  if (!store.data) void store.load($adminApi)
})
</script>

<template>
  <div class="space-y-4">
    <PageHeader
      title="Datenqualität"
      description="Regelbasierte Datenprobleme prüfen und priorisieren."
      ><NuxtLink to="/checks" class="button">Prüfläufe öffnen</NuxtLink></PageHeader
    >
    <p class="muted">
      Aktueller Bestand · unabhängig vom Dashboard-Zeitraum. Gespeicherte Zahlen schließen behobene
      Befunde aus, enthalten aber Zurückstellungen und Ausnahmen.
    </p>
    <RequestState
      :loading="store.loading"
      :error="store.error"
      :has-data="!!store.data"
      :last-success="store.lastSuccess"
      @retry="store.load($adminApi)"
    />
    <div class="grid gap-4 lg:grid-cols-2">
      <QualityOverview :data="store.data" />
      <section class="card p-5">
        <h2 class="font-bold">Orte ohne Geoposition</h2>
        <p class="mt-3 text-sm leading-6 text-slate-600">
          Ein fehlender oder leerer Punkt ist eine Warnung. Kommende Termine erhöhen die Priorität;
          baldige veröffentlichte Termine stehen innerhalb der Warnungen zuerst.
        </p>
        <p class="mt-3 text-sm leading-6 text-slate-600">
          Die Abfrage ist lesend. Es wird kein gespeicherter Prüflauf gestartet und kein Datensatz
          verändert.
        </p>
        <NuxtLink
          to="/findings?rule=venue_missing_geolocation&entity_type=venue&status=open"
          class="button-primary mt-5"
          >Befunde ansehen <AppIcon name="arrow" :size="16"
        /></NuxtLink>
      </section>
    </div>
  </div>
</template>
