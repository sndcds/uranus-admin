<template>
  <EntityDetailPage section="images" record>
    <template #header="{ data }">
      <PageHeader v-if="!data" title="Bild">
        <NuxtLink to="/images" class="action-link">Zur Liste</NuxtLink>
      </PageHeader>
    </template>
    <template #content="{ data, loading }">
      <ImageDetailContent :data="data" :loading="loading" />
    </template>
    <template #after-timeline="{ data }">
      <EntityTechnicalMetadata :data="data" />
    </template>
  </EntityDetailPage>
</template>
