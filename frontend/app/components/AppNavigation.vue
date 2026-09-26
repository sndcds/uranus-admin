<script setup lang="ts">
import KulturbytesLogo from '~/components/KulturbytesLogo.vue'
import { adminNavigationItems, isNavigationActive } from '~/utils/navigation'
const props = withDefaults(defineProps<{ mobile?: boolean; interactive?: boolean }>(), {
  mobile: false,
  interactive: true,
})
const emit = defineEmits<{ navigate: [] }>()
const route = useRoute()
const auth = useAuthStore()
const dashboard = useDashboardStore()
const preferences = useFilterPreferencesStore()
function logout() {
  emit('navigate')
  void auth.logout()
}
</script>

<template>
  <div class="flex h-16 shrink-0 items-center gap-3 border-b border-slate-700 px-4">
    <div class="grid h-10 w-10 place-items-center rounded-xl bg-fuchsia-600 font-black text-white">
      <KulturbytesLogo class="h-7 w-7" />
    </div>
    <div>
      <div class="font-bold">Kulturbytes</div>
      <div class="text-xs text-slate-300">Administration</div>
    </div>
  </div>
  <nav aria-label="Hauptnavigation" class="flex-1 space-y-0.5 overflow-y-auto p-2 text-sm">
    <template v-for="link in adminNavigationItems" :key="link.label">
      <NuxtLink
        :to="link.to"
        :aria-current="isNavigationActive(route.path, link.to) ? 'page' : undefined"
        class="flex items-center min-h-11 gap-3 rounded-lg px-3 py-2"
        :class="
          isNavigationActive(route.path, link.to)
            ? 'bg-fuchsia-900 font-semibold text-white ring-1 ring-inset ring-fuchsia-400/30'
            : 'text-slate-200 hover:bg-slate-800 hover:text-white'
        "
        @click="$emit('navigate')"
      >
        <AppIcon :name="link.icon" /><span>{{ link.label }}</span>
        <span
          v-if="
            link.to === '/findings' &&
            dashboard.data &&
            (dashboard.data.geo_scope_id ?? null) === (preferences.sharedGeoScope?.id ?? null)
          "
          class="ml-auto rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800"
          >{{ dashboard.data.quality.total }}</span
        >
      </NuxtLink>
    </template>
  </nav>
  <NuxtLink v-if="mobile" to="/research" class="button mx-3 mb-3" @click="$emit('navigate')"
    >Recherche</NuxtLink
  >
  <div v-if="mobile" class="shrink-0 space-y-2 border-t border-slate-700 p-3">
    <div class="flex items-center gap-3 rounded-lg bg-slate-800 p-3">
      <div class="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-slate-900 text-white">
        <AppIcon name="lock" :size="16" />
      </div>
      <div class="min-w-0">
        <div class="text-sm font-semibold">Systemadministrator</div>
        <div class="text-xs text-slate-300">Interner Bereich</div>
      </div>
    </div>
    <button
      disabled
      aria-label="+ Datensatz – Uranus-Schreibzugriff nicht eingerichtet"
      class="flex min-h-11 w-full items-center gap-3 rounded-xl border border-slate-700 bg-slate-800 px-3 py-2 text-left text-slate-300 opacity-70"
      title="Anlegen benötigt eine autorisierte Uranus-Verbindung; die Admin-Anmeldung erteilt keine Domain-Schreibrechte."
    >
      <span class="text-lg font-semibold" aria-hidden="true">+</span>
      <span class="min-w-0">
        <span class="block text-sm font-semibold text-slate-100">Datensatz</span>
        <span class="block text-xs">Uranus-Schreibzugriff nicht eingerichtet</span>
      </span>
    </button>
    <button
      class="min-h-11 w-full rounded-lg border border-slate-600 px-3 py-2 text-sm font-semibold text-slate-100 hover:bg-slate-800 disabled:opacity-50"
      :disabled="!props.interactive || auth.loggingOut"
      @click="logout"
    >
      Abmelden
    </button>
  </div>
  <div v-else class="shrink-0 border-t border-slate-700 p-3">
    <div class="flex items-center rounded-lg bg-slate-800 gap-3 p-3">
      <div class="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-slate-900 text-white">
        <AppIcon name="lock" :size="16" />
      </div>
      <div>
        <div class="text-sm font-semibold">Interner Bereich</div>
        <div class="text-xs text-slate-300">Zugriff durch API geprüft</div>
      </div>
    </div>
  </div>
</template>
