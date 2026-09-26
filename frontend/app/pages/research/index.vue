<script setup lang="ts">
definePageMeta({ layout: 'research' })
useHead({ title: 'Kulturbytes Recherche' })
const q = ref('')
</script>
<template>
  <section class="research-landing relative mx-auto max-w-7xl py-6 sm:py-12">
    <div class="research-hero relative overflow-hidden py-4 sm:py-8">
      <div class="relative z-10 max-w-3xl">
        <span
          class="inline-flex items-center gap-2 rounded-full bg-blue-50 px-4 py-2 text-sm text-blue-700"
        >
          <AppIcon name="graph" :size="16" />Kultur verbindet
        </span>
        <PageHeader
          class="research-landing-title mt-6"
          title="Kulturbytes Recherche"
          description="Kultur verstehen. Zusammenhänge entdecken."
        />
        <p class="mt-5 max-w-2xl text-base leading-7 text-slate-600 sm:text-lg">
          Entdecke kulturelle Veranstaltungen, spannende Orte und engagierte Organisationen in
          deiner Region und darüber hinaus.
        </p>
      </div>
      <div
        class="research-illustration pointer-events-none absolute bottom-0 right-0 hidden h-72 w-[45%] xl:block"
        aria-hidden="true"
      >
        <svg class="absolute inset-0 h-full w-full text-blue-200" viewBox="0 0 500 300" fill="none">
          <ellipse cx="270" cy="266" rx="226" ry="23" fill="currentColor" opacity=".15" />
          <path
            d="M55 175Q92 74 170 66T304 43Q397 47 452 164"
            stroke="currentColor"
            stroke-width="2"
            stroke-dasharray="6 6"
          />
          <path
            d="M175 66Q264 78 304 43M175 66Q279 117 334 214"
            stroke="currentColor"
            stroke-width="2"
            stroke-dasharray="6 6"
          />
          <g fill="currentColor" opacity=".38">
            <path
              d="M75 250V194L104 172L134 194V250ZM139 250V169L168 145L197 169V250ZM199 250V195L229 177L257 195V250ZM270 250V149L295 119L320 149V250ZM325 250V185L358 160L391 185V250ZM398 250V207L429 182L460 207V250Z"
            />
            <path d="M156 153V125L168 90L180 125V153ZM283 129V100L295 55L307 100V129Z" />
          </g>
          <g stroke="white" stroke-width="7" opacity=".7">
            <path
              d="M94 204H113M94 224H113M156 182H179M156 204H179M156 226H179M218 211H239M218 232H239M286 162H304M286 186H304M286 210H304M343 198H375M343 220H375M418 220H441"
            />
          </g>
          <path d="M45 253H475" stroke="currentColor" stroke-width="2" />
          <path
            d="M83 268H232M276 278H413M185 290H312"
            stroke="currentColor"
            stroke-width="2"
            opacity=".35"
          />
        </svg>
        <span
          class="absolute left-[18%] top-9 grid h-14 w-14 place-items-center rounded-full bg-blue-100 text-blue-600"
          ><AppIcon name="calendar" :size="28"
        /></span>
        <span
          class="absolute left-[52%] top-0 grid h-14 w-14 place-items-center rounded-full bg-blue-100 text-blue-600"
          ><AppIcon name="pin" :size="28"
        /></span>
        <span
          class="absolute right-5 top-24 grid h-14 w-14 place-items-center rounded-full bg-violet-100 text-violet-600"
          ><AppIcon name="users" :size="28"
        /></span>
      </div>
    </div>
    <form
      class="relative z-10 mt-6 max-w-4xl rounded-xl border border-slate-200 bg-white p-5 shadow-soft sm:p-8"
      role="search"
      @submit.prevent="navigateTo({ path: '/research/search', query: q ? { q } : {} })"
    >
      <h3 class="mb-5 text-xl font-semibold sm:text-2xl">
        <label for="research-start">Was möchtest du entdecken?</label>
      </h3>
      <div class="flex flex-wrap gap-3 sm:flex-nowrap">
        <div class="relative min-w-0 flex-1">
          <AppIcon name="search" class="absolute left-3 top-3.5 text-blue-700" :size="22" />
          <input
            id="research-start"
            v-model="q"
            class="input h-12 pl-11"
            type="search"
            maxlength="120"
            placeholder="Veranstaltungen, Orte, Organisationen …"
          />
        </div>
        <button class="button-primary min-h-12 shrink-0">Suchen</button>
      </div>
      <p class="mt-4 text-sm leading-6 text-slate-600">
        Öffentliche Kulturveranstaltungen recherchieren, Orte erkunden und Zusammenhänge
        nachvollziehen.
      </p>
    </form>
    <div class="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <NuxtLink
        v-for="link in [
          {
            to: 'events',
            title: 'Veranstaltungen',
            text: 'Termine, Inhalte und Quellen zu kulturellen Events in deiner Region.',
            icon: 'calendar',
          },
          {
            to: 'venues',
            title: 'Orte',
            text: 'Veranstaltungsorte und ihre Nutzung entdecken.',
            icon: 'pin',
          },
          {
            to: 'organizations',
            title: 'Organisationen',
            text: 'Veranstalter, ihre Aktivitäten und Beziehungen kennenlernen.',
            icon: 'users',
          },
          {
            to: 'map',
            title: 'Karte',
            text: 'Kulturelle Angebote räumlich entdecken und Zusammenhänge erkunden.',
            icon: 'map',
          },
        ] as const"
        :key="link.to"
        :to="`/research/${link.to}`"
        class="group flex flex-col items-start rounded-xl border border-slate-200 bg-white p-5 hover:border-blue-300 hover:bg-blue-50/30"
      >
        <span
          class="mb-4 grid h-12 w-12 place-items-center rounded-xl"
          :class="
            link.to === 'organizations'
              ? 'bg-violet-50 text-violet-700'
              : 'bg-blue-50 text-blue-700'
          "
          ><AppIcon :name="link.icon" :size="28"
        /></span>
        <h3 class="text-lg font-semibold">{{ link.title }}</h3>
        <p class="mb-5 mt-2 text-sm leading-6 text-slate-600">{{ link.text }}</p>
        <span class="mt-auto flex min-h-11 items-center gap-2 text-sm font-semibold text-blue-700"
          >Entdecken<AppIcon name="arrow" :size="16"
        /></span>
      </NuxtLink>
    </div>
    <div
      class="mt-10 grid gap-5 border-t border-slate-200 pt-6 text-sm sm:grid-cols-2 xl:grid-cols-4"
    >
      <div
        v-for="item in [
          { icon: 'calendar', title: 'Kulturangebote', text: 'Veranstaltungen in deiner Region' },
          { icon: 'link', title: 'Quellen im Blick', text: 'Datenstand und Original-Links' },
          { icon: 'pin', title: 'Neue Perspektiven', text: 'Orte und Zusammenhänge' },
          { icon: 'graph', title: 'Kultur verstehen', text: 'Wissen. Entdecken. Vernetzen.' },
        ] as const"
        :key="item.title"
        class="flex items-center gap-4"
      >
        <AppIcon :name="item.icon" :size="27" class="text-blue-600" />
        <div>
          <p class="font-medium text-slate-800">{{ item.title }}</p>
          <p class="mt-1 text-xs text-slate-500">{{ item.text }}</p>
        </div>
      </div>
    </div>
  </section>
</template>
<style scoped>
@reference '../../assets/css/main.css';
.research-landing-title :deep(h2) {
  @apply text-3xl sm:text-4xl xl:text-5xl;
}
.research-landing-title :deep(p) {
  @apply mt-3 text-lg leading-8 sm:text-2xl;
}
.research-hero {
  background: radial-gradient(ellipse at 90% 70%, var(--color-blue-50), transparent 65%);
}
</style>
