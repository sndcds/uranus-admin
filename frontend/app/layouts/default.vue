<script setup lang="ts">
import { supportsGeoScope } from '~/utils/geo'
import { dateTime } from '~/utils/presentation'
const palette = useTemplateRef('palette')
const preferences = useFilterPreferencesStore()
const route = useRoute()
const auth = useAuthStore()
const interactive = ref(false)
onMounted(() => {
  interactive.value = true
})
const menu = useTemplateRef<HTMLDialogElement>('menu')
const menuButton = useTemplateRef<HTMLButtonElement>('menuButton')
const menuOpen = ref(false)
const now = useState('header-date', () => new Date().toISOString())
const heading = 'Kulturbytes Admin'
function openMenu() {
  menu.value?.showModal()
  menuOpen.value = true
}
function closeMenu() {
  menu.value?.close()
  menuOpen.value = false
  menuButton.value?.focus()
}
</script>

<template>
  <div v-if="auth.isAdmin" :key="auth.revision">
    <GlobalSearchPalette ref="palette" />
    <a
      href="#main-content"
      class="fixed left-4 top-2 z-50 -translate-y-24 rounded-xl bg-white p-3 font-semibold focus:translate-y-0"
      >Zum Inhalt</a
    >
    <aside
      class="fixed inset-y-0 left-0 z-20 w-64 hidden flex-col operations-sidebar border-r border-slate-800 lg:flex"
    >
      <AppNavigation />
    </aside>
    <dialog
      ref="menu"
      aria-label="Mobile Navigation"
      class="fixed inset-y-0 left-0 m-0 h-dvh max-h-none w-80 max-w-[90vw] operations-sidebar border-0 p-0 backdrop:bg-slate-900/40"
      @cancel.prevent="closeMenu"
      @click="$event.target === menu && closeMenu()"
    >
      <div class="relative flex h-full flex-col">
        <button
          class="absolute right-3 top-2.5 grid h-11 w-11 place-items-center rounded-lg"
          aria-label="Navigation schließen"
          @click="closeMenu"
        >
          <AppIcon name="close" /></button
        ><AppNavigation mobile :interactive="interactive" @navigate="closeMenu" />
      </div>
    </dialog>
    <div class="min-h-screen min-w-0 lg:pl-64">
      <header class="sticky top-0 z-10 border-b border-slate-200/80 bg-white/90 backdrop-blur">
        <div data-mobile-app-header class="lg:hidden">
          <div class="flex h-14 min-w-0 items-center gap-3 px-4">
            <button
              ref="menuButton"
              class="grid h-11 w-11 shrink-0 place-items-center rounded-lg border border-slate-200 bg-white"
              aria-label="Navigation öffnen"
              :disabled="!interactive"
              :aria-expanded="menuOpen"
              @click="openMenu"
            >
              <AppIcon name="menu" />
            </button>
            <h1 class="min-w-0 truncate text-base font-semibold">
              {{ heading }}
            </h1>
            <button
              class="ml-auto grid h-11 w-11 shrink-0 place-items-center rounded-lg border border-slate-200 bg-white"
              aria-label="Globale Suche öffnen"
              :disabled="!interactive"
              @click="palette?.show()"
            >
              <AppIcon name="search" />
            </button>
          </div>
          <div class="border-t border-slate-100 px-4 py-2">
            <GeoScopeSelector compact />
          </div>
        </div>
        <div
          class="hidden min-h-16 flex-wrap items-center justify-between gap-x-3 gap-y-1 px-5 py-2 lg:flex"
          data-desktop-app-header
        >
          <h1 class="sr-only">{{ heading }}</h1>
          <button
            class="button min-w-48 justify-start"
            aria-label="Globale Suche öffnen"
            :disabled="!interactive"
            @click="palette?.show()"
          >
            <AppIcon name="search" :size="16" /> Suchen
            <kbd class="ml-auto text-xs font-normal text-slate-500">Ctrl/⌘ K</kbd>
          </button>
          <div class="flex min-w-0 flex-wrap items-center gap-2">
            <span class="text-xs text-slate-600">{{ dateTime(now) }} · Berlin</span>
            <GeoScopeSelector />
            <span class="text-xs text-slate-600">Systemadministrator</span>
            <button
              class="button"
              :disabled="!interactive || auth.loggingOut"
              @click="auth.logout()"
            >
              Abmelden
            </button>
            <button
              disabled
              class="button"
              title="Anlegen benötigt eine autorisierte Uranus-Verbindung; die Admin-Anmeldung erteilt keine Domain-Schreibrechte."
            >
              + Datensatz<span class="text-xs font-normal">Nur Lesen</span>
              <span class="sr-only">Uranus-Schreibzugriff nicht eingerichtet</span>
            </button>
          </div>
        </div>
      </header>
      <main
        id="main-content"
        tabindex="-1"
        class="mx-auto max-w-7xl space-y-4 p-4 sm:space-y-5 sm:p-5"
      >
        <p v-if="preferences.geoScopeError" role="alert" class="text-sm text-amber-800">
          {{ preferences.geoScopeError }}
        </p>
        <p v-if="preferences.sharedGeoScope" class="text-sm text-slate-600" role="status">
          <template v-if="supportsGeoScope(route.path)">
            Gebiet: {{ preferences.sharedGeoScope.name }}.
            <template v-if="route.path === '/' || route.path === '/statistics'">
              Systemweite Kennzahlen sind gekennzeichnet.
            </template>
            <template v-else-if="route.path === '/graph'">
              Das Gebiet filtert nur die Root-Suche. Der Graph zeigt vollständige Beziehungen.
            </template>
            <template v-else-if="route.path === '/findings'">
              Nicht räumlich zuordenbare Hinweise sind ausgeblendet.
            </template>
            <template v-else-if="route.path === '/activity'">
              Nicht räumlich zuordenbare Aktivität wird bei aktivem Gebietsfilter ausgeblendet.
            </template>
            <template v-else>
              Nicht räumlich zuordenbare Datensätze sind bei aktivem Gebietsfilter ausgeschlossen.
            </template>
          </template>
          <template v-else
            >Gebiet: {{ preferences.sharedGeoScope.name }}. Diese Ansicht ist nicht räumlich
            eingeschränkt. Das Gebiet gilt für räumlich zuordenbare Daten.</template
          >
        </p>
        <slot />
      </main>
    </div>
  </div>
</template>
