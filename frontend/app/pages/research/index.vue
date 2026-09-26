<script setup lang="ts">
definePageMeta({ layout: 'research' })
useHead({ title: 'Kulturbytes Recherche' })
const q = ref('')
</script>
<template>
  <section class="mx-auto max-w-4xl space-y-8 py-8 sm:py-16">
    <PageHeader
      title="Kulturbytes Recherche"
      description="Kultur verstehen. Zusammenhänge entdecken."
    />
    <form
      class="panel space-y-4 p-5 sm:p-8"
      role="search"
      @submit.prevent="navigateTo({ path: '/research/search', query: q ? { q } : {} })"
    >
      <label for="research-start" class="type-section-title block"
        >Was möchtest du entdecken?</label
      >
      <div class="flex flex-col gap-3 sm:flex-row">
        <input
          id="research-start"
          v-model="q"
          class="input"
          type="search"
          maxlength="120"
          placeholder="Veranstaltungen, Orte, Organisationen …"
        /><button class="button-primary">Suchen</button>
      </div>
      <p class="type-body">
        Öffentliche Kulturveranstaltungen recherchieren, Orte erkunden und Zusammenhänge
        nachvollziehen.
      </p>
    </form>
    <div class="grid gap-4 sm:grid-cols-3">
      <NuxtLink
        v-for="link in [
          { to: 'events', title: 'Veranstaltungen', text: 'Termine, Inhalte und Quellen' },
          { to: 'venues', title: 'Orte', text: 'Veranstaltungsorte und ihre Nutzung' },
          {
            to: 'organizations',
            title: 'Organisationen',
            text: 'Veranstalter und ihre Aktivitäten',
          },
        ]"
        :key="link.to"
        :to="`/research/${link.to}`"
        class="panel space-y-2 p-5 hover:bg-slate-50"
        ><h3 class="type-section-title">{{ link.title }}</h3>
        <p class="type-body">{{ link.text }}</p>
        <span class="action-link">Entdecken →</span></NuxtLink
      >
    </div>
  </section>
</template>
