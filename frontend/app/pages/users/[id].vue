<template>
  <EntityDetailPage section="users" record>
    <template #header="{ data }">
      <PageHeader v-if="!data" title="Benutzer">
        <NuxtLink to="/users" class="action-link">Zur Liste</NuxtLink>
      </PageHeader>
    </template>
    <template #content="{ data, loading }">
      <UserDetailContent :data="data" :loading="loading" />
    </template>
    <template #after-timeline="{ data }">
      <EntityTechnicalMetadata :data="data" />
    </template>
  </EntityDetailPage>
</template>
