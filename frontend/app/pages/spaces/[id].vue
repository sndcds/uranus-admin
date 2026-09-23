<template>
  <EntityDetailPage section="spaces" record>
    <template #header="{ data }">
      <EntityHero v-if="data" :item="data.item" section="spaces">
        <template #context><SpaceDetailContext :data="data" /></template>
      </EntityHero>
      <PageHeader v-else title="Raum">
        <NuxtLink to="/spaces" class="action-link">Zur Liste</NuxtLink>
      </PageHeader>
    </template>
    <template #content="{ data, loading }">
      <SpaceDetailContent :data="data" :loading="loading" />
    </template>
    <template #after-timeline="{ data }">
      <EntityTechnicalMetadata :data="data" />
    </template>
  </EntityDetailPage>
</template>
