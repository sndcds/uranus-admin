<template>
  <div class="operations-page">
    <PageHeader title="Social Publishing" description="Veröffentlichungen und geplante Beiträge">
      <NuxtLink to="/" class="button">Zur Übersicht</NuxtLink>
    </PageHeader>
    <EmptyState message="Social-Publishing-Daten sind derzeit nicht verfügbar.">
      <p class="type-body">
        Die angebundene Admin-API liefert noch keine Social Posts, Targets, Publications oder
        Scheduling-Zustände.
      </p>
    </EmptyState>
    <RecordSection title="Verfügbarkeit" surface="panel">
      <DetailFacts
        :items="[
          { label: 'Social Posts', value: 'Nicht verfügbar' },
          { label: 'Targets und Accounts', value: 'Nicht verfügbar' },
          { label: 'Publication History', value: 'Nicht verfügbar' },
          { label: 'Scheduling und Worker-Status', value: 'Nicht verfügbar' },
        ]"
      />
      <p class="type-body">
        Fehlende Daten erlauben keine Aussage über geplante, laufende, erfolgreiche, fehlgeschlagene
        oder ungewisse Veröffentlichungen.
      </p>
    </RecordSection>
  </div>
</template>
