<script setup lang="ts">
definePageMeta({ layout: 'research' })
useHead({
  title: 'Kulturbytes Recherche',
  meta: [
    {
      name: 'viewport',
      content: 'width=device-width, initial-scale=1, interactive-widget=resizes-content',
    },
  ],
})
</script>

<template>
  <ResearchQuestion class="research-landing mx-auto w-full max-w-[86rem]">
    <template #welcome>
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
      </section>
    </template>
  </ResearchQuestion>
</template>

<style scoped>
@reference '../../assets/css/main.css';
.research-landing {
  background: radial-gradient(ellipse at 50% 35%, var(--color-blue-50), transparent 66%);
}
.research-hero-heading {
  max-width: 51rem;
  padding-top: 1.5rem;
  padding-bottom: 1rem;
}
.research-hero-title {
  font-size: 30px;
  line-height: 1.15;
}
.research-hero-description {
  line-height: 26px;
}
@media (min-width: 640px) {
  .research-hero-title {
    font-size: 40px;
    line-height: 44px;
  }
}
</style>
