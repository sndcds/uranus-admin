<template>
  <EntityDetailPage section="events" record>
    <template #header="{ data }">
      <EntityHero
        v-if="data"
        :item="data.item"
        section="events"
        organization-label="Veranstalter"
      />
      <PageHeader v-else title="Veranstaltung">
        <NuxtLink to="/events" class="action-link">Zur Liste</NuxtLink>
      </PageHeader>
    </template>
    <template #content="{ data, loading }">
      <EventDetailContent :data="data" :loading="loading" />
    </template>
    <template #after-timeline="{ data }">
      <EntityTechnicalMetadata :data="data" />
    </template>
  </EntityDetailPage>
</template>
