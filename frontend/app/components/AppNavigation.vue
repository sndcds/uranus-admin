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
  <div
    class="flex shrink-0 items-center gap-3 border-b border-slate-100 px-6"
    :class="mobile ? 'h-16' : 'h-20'"
  >
    <div class="grid h-10 w-10 place-items-center rounded-2xl bg-fuchsia-600 font-black text-white">
      <KulturbytesLogo class="h-7 w-7" />
    </div>
    <div>
      <div class="font-bold">Kulturbytes</div>
      <div class="text-xs text-slate-500">Administration</div>
    </div>
  </div>
  <nav aria-label="Hauptnavigation" class="flex-1 space-y-1 overflow-y-auto p-4 text-sm">
    <template v-for="link in adminNavigationItems" :key="link.label">
      <NuxtLink
        :to="link.to"
        :aria-current="isNavigationActive(route.path, link.to) ? 'page' : undefined"
        class="flex items-center gap-3 rounded-xl px-4 py-3"
        :class="
          isNavigationActive(route.path, link.to)
            ? 'bg-fuchsia-50 font-semibold text-fuchsia-700'
            : 'text-slate-600 hover:bg-slate-50'
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
  <div v-if="mobile" class="shrink-0 space-y-2 border-t border-slate-200 p-4">
    <div class="flex items-center gap-3 rounded-xl bg-slate-50 p-3">
      <div class="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-slate-900 text-white">
        <AppIcon name="lock" :size="16" />
      </div>
      <div class="min-w-0">
        <div class="text-sm font-semibold">Systemadministrator</div>
        <div class="text-xs text-slate-500">Interner Bereich</div>
      </div>
    </div>
    <button
      disabled
      aria-label="+ Datensatz – Uranus-Schreibzugriff nicht eingerichtet"
      class="flex min-h-11 w-full items-center gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2 text-left text-slate-500 opacity-70"
      title="Anlegen benötigt eine autorisierte Uranus-Verbindung; die Admin-Anmeldung erteilt keine Domain-Schreibrechte."
    >
      <span class="text-lg font-semibold" aria-hidden="true">+</span>
      <span class="min-w-0">
        <span class="block text-sm font-semibold text-slate-700">Datensatz</span>
        <span class="block text-xs">Uranus-Schreibzugriff nicht eingerichtet</span>
      </span>
    </button>
    <button
      class="button min-h-11 w-full"
      :disabled="!props.interactive || auth.loggingOut"
      @click="logout"
    >
      Abmelden
    </button>
  </div>
  <div v-else class="shrink-0 border-t border-slate-100 p-4">
    <div class="flex items-center rounded-xl bg-slate-50 gap-3 p-3">
      <div class="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-slate-900 text-white">
        <AppIcon name="lock" :size="16" />
      </div>
      <div>
        <div class="text-sm font-semibold">Interner Bereich</div>
        <div class="text-xs text-slate-500">Zugriff durch API geprüft</div>
      </div>
    </div>
  </div>
</template>
