<script setup lang="ts">
definePageMeta({ layout: 'research' })
useHead({ title: 'Kulturbytes Recherche' })
const discoveries = [
  {
    to: 'events',
    label: 'Veranstaltungen',
    icon: 'calendar',
    description: 'Termine, Inhalte und Quellen zu kulturellen Events entdecken.',
  },
  {
    to: 'venues',
    label: 'Orte',
    icon: 'pin',
    description: 'Veranstaltungsorte und ihre Nutzung kennenlernen.',
  },
  {
    to: 'organizations',
    label: 'Organisationen',
    icon: 'organization',
    description: 'Veranstalter, ihre Aktivitäten und Beziehungen erkunden.',
  },
  {
    to: 'map',
    label: 'Karte',
    icon: 'map',
    description: 'Kulturelle Angebote räumlich entdecken.',
  },
] as const
</script>

<template>
  <div class="research-landing mx-auto max-w-7xl py-6 sm:py-8">
    <section aria-labelledby="research-heading">
      <header class="mx-auto mb-6 max-w-3xl text-center">
        <span
          class="inline-flex items-center gap-2 rounded-full bg-blue-50 px-4 py-2 text-sm text-blue-700"
        >
          <AppIcon name="graph" :size="16" />Kultur verbindet
        </span>
        <h2
          id="research-heading"
          class="mt-5 text-3xl font-semibold leading-tight tracking-tight text-slate-950 sm:text-4xl"
        >
          Was möchtest du über Kultur in deiner Region erfahren?
        </h2>
        <p class="mx-auto mt-4 max-w-2xl text-base leading-relaxed text-slate-600 sm:text-lg">
          Stelle eine Frage zu Veranstaltungen, Orten oder Organisationen und erhalte fundierte
          Antworten aus unseren Daten.
        </p>
      </header>
      <ResearchQuestion />
    </section>

    <section aria-labelledby="research-discover" class="mt-12 border-t border-slate-200 pt-6">
      <h2 id="research-discover" class="text-xl font-semibold text-slate-900">Kultur entdecken</h2>
      <p class="mt-1 text-sm text-slate-600">Daten, Orte und Zusammenhänge selbst erkunden.</p>
      <div class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <NuxtLink
          v-for="item in discoveries"
          :key="item.to"
          :to="`/research/${item.to}`"
          class="group flex gap-4 rounded-xl border border-slate-200 bg-white p-5 transition-colors hover:border-blue-300 hover:bg-blue-50/40"
        >
          <span
            class="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue-700"
          >
            <AppIcon :name="item.icon" :size="24" />
          </span>
          <div class="flex min-w-0 flex-col items-start">
            <h3 class="font-semibold text-slate-900">{{ item.label }}</h3>
            <p class="mt-2 text-sm leading-relaxed text-slate-600">{{ item.description }}</p>
            <span
              class="mt-auto inline-flex min-h-11 items-center gap-2 pt-3 text-sm font-medium text-blue-700"
            >
              Entdecken<AppIcon name="arrow" :size="16" />
            </span>
          </div>
        </NuxtLink>
      </div>
    </section>
  </div>
</template>

<style scoped>
@reference '../../assets/css/main.css';
.research-landing {
  background: radial-gradient(ellipse at 50% 18%, var(--color-blue-50), transparent 60%);
}
</style>
