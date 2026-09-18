<script setup lang="ts">
import { supportsGeoScope } from '~/utils/geo'
import { dateTime } from '~/utils/presentation'
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
    <a
      href="#main-content"
      class="fixed left-4 top-2 z-50 -translate-y-24 rounded-xl bg-white p-3 font-semibold focus:translate-y-0"
      >Zum Inhalt</a
    >
    <aside
      class="fixed inset-y-0 left-0 z-20 w-64 hidden flex-col border-r border-slate-200 bg-white lg:flex"
    >
      <AppNavigation />
    </aside>
    <dialog
      ref="menu"
      aria-label="Mobile Navigation"
      class="fixed inset-y-0 left-0 m-0 h-dvh max-h-none w-80 max-w-[90vw] border-0 bg-white p-0 backdrop:bg-slate-900/40"
      @cancel.prevent="closeMenu"
      @click="$event.target === menu && closeMenu()"
    >
      <div class="relative flex h-full flex-col">
        <button
          class="absolute right-3 top-6 rounded-lg p-2"
          aria-label="Navigation schließen"
          @click="closeMenu"
        >
          <AppIcon name="close" /></button
        ><AppNavigation @navigate="closeMenu" />
      </div>
    </dialog>
    <div class="min-h-screen min-w-0 lg:pl-64">
      <header class="sticky top-0 z-10 border-b border-slate-200/80 bg-white/90 backdrop-blur">
        <div class="flex min-h-16 flex-wrap items-center justify-between gap-3 px-5 py-3 sm:px-8">
          <div class="flex min-w-0 items-center gap-3">
            <button
              ref="menuButton"
              class="rounded-xl border border-slate-200 p-2 lg:hidden"
              aria-label="Navigation öffnen"
              :disabled="!interactive"
              :aria-expanded="menuOpen"
              @click="openMenu"
            >
              <AppIcon name="menu" />
            </button>
            <div>
              <div class="text-xs font-medium uppercase tracking-wider text-slate-500">
                {{ dateTime(now) }} · Berlin
              </div>
              <h1 class="text-base font-semibold">
                {{ heading }}
              </h1>
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-3">
            <GeoScopeSelector />
            <span class="text-sm text-slate-600">Systemadministrator</span>
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
              + Datensatz<span class="block text-xs font-normal"
                >Uranus-Schreibzugriff nicht eingerichtet</span
              >
            </button>
          </div>
        </div>
      </header>
      <main id="main-content" tabindex="-1" class="mx-auto max-w-7xl space-y-5 p-5 sm:p-8">
        <p v-if="preferences.geoScopeError" role="alert" class="text-sm text-amber-800">
          {{ preferences.geoScopeError }}
        </p>
        <p v-if="preferences.sharedGeoScope" class="text-sm text-slate-600" role="status">
          <template v-if="supportsGeoScope(route.path)"
            >Nicht räumlich zuordenbare Datensätze sind bei aktivem Gebietsfilter
            ausgeschlossen.</template
          >
          <template v-else
            >Gebiet: {{ preferences.sharedGeoScope.name }}. Diese Ansicht ist nicht räumlich
            eingeschränkt. Der Gebietsfilter gilt derzeit für Listen und Suche von Veranstaltungen,
            Orten, Räumen und Organisationen.</template
          >
        </p>
        <slot />
      </main>
    </div>
  </div>
</template>
