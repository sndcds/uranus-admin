<template>
  <EntityDetailPage section="organizations" record>
    <template #header="{ data }">
      <EntityHero v-if="data" :item="data.item" section="organizations">
        <template #context
          ><p v-if="data.item.subtitle?.trim()" class="type-body mt-2 break-words">
            {{ data.item.subtitle }}
          </p></template
        >
      </EntityHero>
      <PageHeader v-else title="Organisation">
        <NuxtLink to="/organizations" class="action-link">Zur Liste</NuxtLink>
      </PageHeader>
    </template>
    <template #content="{ data, loading }">
      <OrganizationDetailContent :data="data" :loading="loading" />
    </template>
    <template #after-timeline="{ data }">
      <EntityTechnicalMetadata :data="data" />
    </template>
  </EntityDetailPage>
</template>
