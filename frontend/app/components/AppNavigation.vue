<script setup lang="ts">
import KulturbytesLogo from '~/components/KulturbytesLogo.vue'
import { isNavigationActive } from '~/utils/navigation'
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
const links = [
  { label: 'Übersicht', icon: 'home', to: '/' },
  { label: 'Inbox', icon: 'list', to: '/inbox' },
  { label: 'Partneranfragen', icon: 'organization', to: '/queues/partner_requests' },
  { label: 'Einladungen', icon: 'users', to: '/queues/team_invitations' },
  { label: 'Aktivierungen', icon: 'users', to: '/queues/user_activation' },
  { label: 'Benachrichtigungen', icon: 'list', to: '/notifications' },
  { label: 'Prüfläufe', icon: 'history', to: '/checks' },
  { label: 'Aktivität', icon: 'history', to: '/activity' },
  { label: 'Arbeitsliste', icon: 'list', to: '/findings' },
  { label: 'Markierungen', icon: 'list', to: '/marks' },
  { label: 'Veranstaltungen', icon: 'calendar', to: '/events' },
  { label: 'Orte & Räume', icon: 'pin', to: '/venues' },
  { label: 'Organisationen', icon: 'organization', to: '/organizations' },
  { label: 'Benutzer & Teams', icon: 'users', to: '/users' },
  { label: 'Bilder', icon: 'image', to: '/images' },
  { label: 'Beziehungsgraph', icon: 'graph', to: '/graph' },
  { label: 'SQL Console', icon: 'code', to: '/sql' },
  { label: 'Statistiken', icon: 'chart', to: '/statistics' },
] as const
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
    <template v-for="link in links" :key="link.label">
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
    <div class="pt-5 text-xs font-semibold uppercase tracking-wider text-slate-500">Qualität</div>
    <NuxtLink
      to="/quality"
      :aria-current="isNavigationActive(route.path, '/quality') ? 'page' : undefined"
      class="flex items-center gap-3 rounded-xl px-4 py-3"
      :class="
        isNavigationActive(route.path, '/quality')
          ? 'bg-fuchsia-50 font-semibold text-fuchsia-700'
          : 'text-slate-600 hover:bg-slate-50'
      "
      @click="$emit('navigate')"
      ><AppIcon name="quality" />Datenqualität</NuxtLink
    >
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
