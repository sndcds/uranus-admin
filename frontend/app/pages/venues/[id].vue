<template>
  <EntityDetailPage section="venues" record>
    <template #header="{ data }">
      <EntityHero v-if="data" :item="data.item" section="venues">
        <template #context
          ><p v-if="data.item.organization_name?.trim()" class="type-body mt-2 break-words">
            Organisation: {{ data.item.organization_name }}
          </p></template
        >
      </EntityHero>
      <PageHeader v-else title="Ort">
        <NuxtLink to="/venues" class="action-link">Zur Liste</NuxtLink>
      </PageHeader>
    </template>
    <template #content="{ data, loading }">
      <VenueDetailContent :data="data" :loading="loading" />
    </template>
    <template #after-timeline="{ data }">
      <EntityTechnicalMetadata :data="data" />
    </template>
  </EntityDetailPage>
</template>
