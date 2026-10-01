<script setup lang="ts">
definePageMeta({ layout: 'research' })
useHead({ title: 'Kulturbytes Recherche' })
const discoveries = [
  {
    to: 'events',
    label: 'Veranstaltungen',
    icon: 'calendar',
    description: 'Termine, Inhalte und Quellen zu kulturellen Events in deiner Region.',
  },
  {
    to: 'venues',
    label: 'Orte',
    icon: 'pin',
    description: 'Veranstaltungsorte und ihre Nutzung entdecken.',
  },
  {
    to: 'organizations',
    label: 'Organisationen',
    icon: 'users',
    description: 'Veranstalter, ihre Aktivitäten und Beziehungen kennenlernen.',
  },
  {
    to: 'map',
    label: 'Karte',
    icon: 'map',
    description: 'Kulturelle Angebote räumlich entdecken und Zusammenhänge erkunden.',
  },
] as const
</script>

<template>
  <div class="research-landing mx-auto max-w-[86rem] py-6">
    <section aria-labelledby="research-heading" class="research-hero relative">
      <ResearchHeroIllustration side="left" />
      <ResearchHeroIllustration side="right" />
      <header class="research-hero-heading relative z-10 mx-auto text-center">
        <span
          class="inline-flex min-h-10 items-center gap-2 rounded-full bg-blue-50 px-4 py-2 text-sm text-blue-700"
        >
          <AppIcon name="sparkles" :size="18" />KI-gestützte Kulturanalyse
        </span>
        <h2
          id="research-heading"
          class="research-hero-title mt-6 font-bold tracking-tight text-slate-900"
        >
          Was möchtest du über<br class="hidden sm:block" />
          Kultur in deiner Region erfahren?
        </h2>
        <p class="research-hero-description mx-auto mt-3 text-base text-slate-600 sm:text-lg">
          Stelle eine Frage zu Veranstaltungen, Orten oder Organisationen<br
            class="hidden sm:block"
          />
          und erhalte fundierte Antworten aus unseren Daten.
        </p>
      </header>
      <ResearchQuestion class="research-question-workspace relative z-10" />
    </section>

    <section
      aria-labelledby="research-discover"
      class="research-discovery border-t border-slate-200 pt-4"
    >
      <div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div>
          <h2 id="research-discover" class="text-xl font-semibold text-slate-900">
            Kultur entdecken
          </h2>
          <p class="mt-1 text-sm text-slate-600">
            Daten, Orte und Zusammenhänge auf neue Weise erkunden.
          </p>
        </div>
        <NuxtLink
          to="/research/search"
          class="inline-flex min-h-11 items-center gap-2 text-sm font-medium text-blue-700 hover:underline"
        >
          Alle Bereiche ansehen<AppIcon name="arrow" :size="16" />
        </NuxtLink>
      </div>
      <div class="mt-3.5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <NuxtLink
          v-for="item in discoveries"
          :key="item.to"
          :to="`/research/${item.to}`"
          class="research-discovery-card group flex gap-5 rounded-xl border border-slate-200 bg-white p-4 transition-colors hover:border-blue-300 hover:bg-blue-50/40"
        >
          <span
            class="grid h-13 w-13 shrink-0 place-items-center rounded-xl"
            :class="
              item.to === 'organizations'
                ? 'bg-violet-50 text-violet-600'
                : 'bg-blue-50 text-blue-700'
            "
          >
            <AppIcon :name="item.icon" :size="28" />
          </span>
          <div class="flex min-w-0 flex-col items-start">
            <h3 class="text-sm font-semibold text-slate-900">{{ item.label }}</h3>
            <p class="mt-2 text-sm leading-[1.45] text-slate-600">{{ item.description }}</p>
            <span
              class="mt-auto inline-flex min-h-8 items-center gap-2 pt-2 text-sm font-medium text-blue-700"
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
  background: radial-gradient(ellipse at 50% 35%, var(--color-blue-50), transparent 66%);
}
.research-hero-heading {
  max-width: 51rem;
  margin-bottom: 25px;
}
.research-hero-title {
  font-size: 30px;
  line-height: 1.15;
}
.research-hero-description {
  line-height: 26px;
}
.research-discovery {
  margin-top: 5px;
}
.research-discovery-card {
  min-height: 160px;
}
@media (min-width: 640px) {
  .research-hero-title {
    font-size: 40px;
    line-height: 44px;
  }
}

@media (min-width: 1280px) {
  .research-hero-heading,
  .research-question-workspace {
    left: -20px;
  }
}
</style>
