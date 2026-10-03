<script setup lang="ts">
import { researchAnswerMode } from '~/utils/research-answer'
const auth = useAuthStore()
const route = useRoute()
const menu = useTemplateRef('menu')
const accountMenu = useTemplateRef('accountMenu')
const header = useTemplateRef('header')
const headerHeight = ref(72)
let headerObserver: ResizeObserver | undefined
const query = ref('')
const mode = ref<'classic' | 'semantic'>('classic')
const semanticLoading = useState('research-semantic-loading', () => false)
const interactive = ref(false)
const answering = computed(
  () => route.path === '/research/search' && researchAnswerMode(route.query),
)
const collection = computed(() =>
  /^\/research\/(search|map|events|venues|organizations)$/.test(route.path),
)
const account = computed(() => {
  const subject = auth.session?.subject.replace(/^admin:/, '') || ''
  return /^[0-9a-f]{8}-/i.test(subject)
    ? `Konto ${subject.slice(0, 8)}`
    : subject || 'Recherche-Konto'
})
let timer: ReturnType<typeof setTimeout> | undefined
onMounted(() => {
  interactive.value = true
  headerObserver = new ResizeObserver(() => {
    headerHeight.value = header.value?.getBoundingClientRect().height ?? 72
  })
  if (header.value) headerObserver.observe(header.value)
})
watch(
  () => route.fullPath,
  () => {
    clearTimeout(timer)
    mode.value = route.query.search_mode === 'semantic' ? 'semantic' : 'classic'
    query.value = typeof route.query.q === 'string' ? route.query.q : ''
  },
  { immediate: true },
)
function search() {
  clearTimeout(timer)
  if (semanticLoading.value || answering.value) return
  const searchMode = mode.value === 'semantic' ? 'semantic' : undefined
  return navigateTo(
    collection.value
      ? {
          path: searchMode ? '/research/search' : route.path,
          query: {
            ...route.query,
            q: query.value || undefined,
            page: undefined,
            search_mode: searchMode,
            ...(searchMode
              ? { entity_type: undefined, sort: undefined, page_size: undefined }
              : {}),
          },
        }
      : {
          path: '/research/search',
          query: { ...(query.value ? { q: query.value } : {}), search_mode: searchMode },
        },
  )
}
watch(mode, () => clearTimeout(timer))
watch(query, (value) => {
  clearTimeout(timer)
  if (answering.value || mode.value === 'semantic' || route.query.search_mode === 'semantic') return
  if (!interactive.value || !collection.value || value === (route.query.q ?? '')) return
  timer = setTimeout(() => {
    void search()
  }, 300)
})
onBeforeUnmount(() => {
  headerObserver?.disconnect()
  clearTimeout(timer)
})
</script>
<template>
  <div
    v-if="auth.canResearch"
    :key="auth.revision"
    class="research-workspace min-h-screen bg-white"
    :class="{ 'research-composer-workspace': route.path === '/research' }"
  >
    <a
      href="#main-content"
      class="fixed left-4 top-2 z-50 -translate-y-24 rounded-lg bg-white p-3 focus:translate-y-0"
      >Zum Inhalt</a
    >
    <header
      ref="header"
      class="research-header shrink-0 sticky top-0 z-20 border-b border-slate-200 bg-slate-50/95"
    >
      <div
        class="flex flex-wrap items-center gap-3 px-4 py-3 lg:min-h-[4.5rem] lg:flex-nowrap lg:gap-6 lg:px-6"
      >
        <button
          class="research-icon-button research-menu-button"
          aria-label="Recherche-Menü öffnen"
          :disabled="!interactive"
          @click="menu?.open()"
        >
          <AppIcon name="menu" />
        </button>
        <NuxtLink to="/research" class="flex min-w-0 items-center gap-3 lg:shrink-0">
          <KulturbytesLogo class="h-8 w-8 shrink-0 text-blue-900" />
          <div>
            <h1 class="text-sm font-bold tracking-tight sm:text-xl">Kulturbytes Recherche</h1>
            <p class="hidden text-xs text-slate-600 sm:block">
              Kultur verstehen. Zusammenhänge entdecken.
            </p>
          </div>
        </NuxtLink>
        <form
          v-if="route.path !== '/research' && !answering"
          role="search"
          aria-label="Globale Recherche-Suche"
          class="research-global-search relative order-3 w-full lg:order-none lg:mx-auto lg:max-w-2xl lg:flex-1"
          @submit.prevent="search"
        >
          <label for="research-global-q" class="sr-only"
            >Veranstaltungen, Orte, Organisationen suchen</label
          >
          <input
            id="research-global-q"
            v-model="query"
            :disabled="!interactive"
            class="input h-11 pl-11 pr-3"
            type="search"
            maxlength="120"
            :required="mode === 'semantic'"
            :minlength="mode === 'semantic' ? 2 : undefined"
            placeholder="Veranstaltungen, Orte, Organisationen suchen …"
          />
          <button
            class="research-icon-button absolute top-0 left-0 text-slate-500"
            :disabled="!interactive || semanticLoading"
            aria-label="Recherche starten"
          >
            <AppIcon name="search" />
          </button>
          <ResearchSearchMode v-model="mode" :disabled="!interactive" />
        </form>
        <button
          class="ml-auto flex min-h-11 shrink-0 items-center gap-3 rounded-lg text-left"
          aria-label="Nutzerbereich öffnen"
          :disabled="!interactive"
          @click="accountMenu?.open()"
        >
          <span class="grid h-10 w-10 place-items-center rounded-full bg-blue-100 text-blue-900"
            ><AppIcon name="user"
          /></span>
          <span class="hidden max-w-40 sm:block"
            ><span class="block truncate text-sm font-medium">{{ account }}</span
            ><span class="text-xs text-slate-600">Recherche</span></span
          >
          <AppIcon name="down" :size="16" class="hidden text-blue-950 sm:block" />
        </button>
      </div>
    </header>
    <aside
      :style="{ top: `${headerHeight}px` }"
      class="fixed bottom-0 hidden w-56 border-r border-slate-200 bg-slate-50/70 lg:block"
    >
      <ResearchNavigation />
    </aside>
    <AppModal ref="menu" title="Kulturbytes Recherche"
      ><ResearchNavigation @navigate="menu?.close()"
    /></AppModal>
    <AppModal ref="accountMenu" title="Dein Recherche-Konto">
      <p class="mt-4 break-words font-medium">{{ account }}</p>
      <p class="mt-1 text-sm text-slate-600">
        {{ auth.isAdmin ? 'Systemadministrator · Recherche' : 'Recherche' }}
      </p>
      <button class="action-link mt-4" :disabled="auth.loggingOut" @click="auth.logout()">
        <AppIcon name="logout" />Abmelden
      </button>
    </AppModal>
    <main id="main-content" tabindex="-1" class="min-w-0 p-4 lg:ml-56 lg:px-10 lg:py-5">
      <div class="mx-auto max-w-[100rem] space-y-5"><slot /></div>
    </main>
  </div>
</template>

<style>
@reference '../assets/css/main.css';
/* Only the question workspace owns a scrollable content row and a composer footer.
   The existing main margin reserves the sidebar; neither row uses viewport width. */
.research-composer-workspace {
  display: flex;
  flex-direction: column;
  height: 100dvh;
  min-height: 0;
  overflow: hidden;
}
.research-composer-workspace > main,
.research-composer-workspace > main > div {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.research-composer-workspace > main > div {
  width: 100%;
}
/* Research presentation is confined to its own layout, including native dialogs. */
.research-workspace :focus-visible {
  @apply outline-blue-700;
}
.research-workspace .button-primary {
  @apply bg-blue-700 font-medium hover:bg-blue-800;
}
.research-workspace .button {
  @apply font-medium;
}
.research-workspace :is(.action-link, .admin-table a, .prose-admin a) {
  @apply text-blue-700;
}
.research-workspace .type-page-title {
  @apply text-3xl;
}
.research-workspace .type-record-title {
  @apply text-2xl sm:text-3xl;
}
.research-workspace .research-icon-button {
  @apply inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg hover:bg-blue-50 disabled:opacity-50;
}
.research-workspace .research-chip {
  @apply inline-flex min-h-11 items-center gap-2 rounded-md text-xs text-blue-900;
}
.research-workspace .research-chip > span {
  @apply inline-flex items-center gap-2 rounded-md border border-blue-100 bg-blue-50 px-2 py-1;
}
.research-workspace .research-type {
  @apply bg-blue-50 text-blue-700;
}
.research-workspace .research-toggle {
  @apply inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5;
}
.research-workspace .research-toggle button {
  @apply inline-flex min-h-11 items-center justify-center gap-2 rounded-md px-4 text-sm text-slate-600;
}
.research-workspace .research-toggle button[aria-pressed='true'] {
  @apply bg-blue-50 text-blue-700 shadow-[inset_0_-2px_0_0_var(--color-blue-600)];
}
.research-workspace .research-info {
  @apply flex flex-wrap items-center justify-between gap-3 rounded-lg bg-blue-50/70 p-4 text-sm text-slate-600;
}
.research-workspace .research-dossier {
  @apply space-y-6;
}
.research-workspace .research-dossier .section-plain > header {
  @apply flex flex-wrap items-start justify-between gap-3;
}
.research-workspace .research-dossier .type-section-title {
  @apply text-xl;
}
.research-workspace .candidate-map-marker[aria-pressed='true'] {
  @apply border-blue-800 bg-blue-600 text-white;
}
.research-workspace .candidate-map-marker:focus-visible {
  @apply outline-blue-700;
}
@media (min-width: 1024px) {
  .research-workspace .research-menu-button {
    display: none;
  }
}
</style>
