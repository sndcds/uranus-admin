<script setup lang="ts">
const auth = useAuthStore()
const route = useRoute()
const menu = useTemplateRef('menu')
const query = ref('')
const interactive = ref(false)
onMounted(() => {
  interactive.value = true
})
watch(
  () => route.query.q,
  (q) => {
    query.value = typeof q === 'string' ? q : ''
  },
  { immediate: true },
)
function search() {
  return navigateTo({ path: '/research/search', query: query.value ? { q: query.value } : {} })
}
</script>
<template>
  <div v-if="auth.canResearch" :key="auth.revision" class="min-h-screen">
    <a
      href="#main-content"
      class="fixed left-4 top-2 z-50 -translate-y-24 rounded-xl bg-white p-3 focus:translate-y-0"
      >Zum Inhalt</a
    >
    <header class="sticky top-0 z-20 border-b border-slate-200 bg-white">
      <div class="flex flex-wrap items-center gap-3 px-4 py-3 lg:px-5">
        <button
          class="button lg:hidden"
          aria-label="Recherche-Menü öffnen"
          :disabled="!interactive"
          @click="menu?.open()"
        >
          <AppIcon name="menu" />
        </button>
        <NuxtLink to="/research" class="flex min-w-0 items-center gap-3">
          <KulturbytesLogo class="h-8 w-8 text-slate-800" />
          <div>
            <h1 class="text-base font-bold sm:text-lg">Kulturbytes Recherche</h1>
            <p class="hidden text-xs text-slate-600 sm:block">
              Kultur verstehen. Zusammenhänge entdecken.
            </p>
          </div>
        </NuxtLink>
        <form
          role="search"
          aria-label="Globale Recherche-Suche"
          class="order-3 flex w-full gap-2 lg:order-none lg:ml-5 lg:w-auto lg:flex-1"
          @submit.prevent="search"
        >
          <label for="research-global-q" class="sr-only"
            >Veranstaltungen, Orte, Organisationen suchen</label
          >
          <input
            id="research-global-q"
            v-model="query"
            class="input"
            type="search"
            maxlength="120"
            placeholder="Veranstaltungen, Orte, Organisationen suchen …"
          />
          <button class="button" aria-label="Recherche starten"><AppIcon name="search" /></button>
        </form>
        <div class="ml-auto flex items-center gap-2">
          <span class="hidden text-xs text-slate-600 sm:inline">{{
            auth.isAdmin ? 'Systemadministrator · Recherche' : 'Recherche'
          }}</span
          ><button
            class="button"
            :disabled="!interactive || auth.loggingOut"
            @click="auth.logout()"
          >
            Abmelden
          </button>
        </div>
      </div>
    </header>
    <aside class="fixed bottom-0 top-20 hidden w-56 border-r border-slate-200 bg-white lg:block">
      <ResearchNavigation />
    </aside>
    <AppModal ref="menu" title="Kulturbytes Recherche"
      ><ResearchNavigation @navigate="menu?.close()"
    /></AppModal>
    <main id="main-content" tabindex="-1" class="min-w-0 p-4 lg:ml-56 lg:p-5">
      <div class="mx-auto max-w-[96rem] space-y-4"><slot /></div>
    </main>
  </div>
</template>
