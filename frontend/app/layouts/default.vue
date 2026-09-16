<script setup lang="ts">
import { dateTime } from '~/utils/presentation'
import { failure } from '#shared/errors'
import { periodSchema } from '#shared/contracts'
const route = useRoute()
const dashboard = useDashboardStore()
const findings = useFindingsStore()
const { $adminApi } = useNuxtApp()
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
const accessRevision = useState('admin-access-revision', () => 0)
function clearAccess() {
  accessRevision.value++
  dashboard.reset()
  findings.reset()
}
const authStatus = useState('admin-auth-status', () => 0)
let cleared = false
$adminApi.onAccessLost((status) => {
  authStatus.value = status
  if (!cleared) {
    cleared = true
    clearAccess()
    dashboard.error = failure(status)
    findings.error = failure(status)
  }
})
async function accessChanged() {
  authStatus.value = 0
  cleared = false
  clearAccess()
  await Promise.all([dashboard.load($adminApi), findings.load($adminApi)])
}
</script>

<template>
  <div>
    <a
      href="#main-content"
      class="fixed left-4 top-2 z-50 -translate-y-24 rounded-xl bg-white p-3 font-semibold focus:translate-y-0"
      >Zum Inhalt</a
    >
    <aside
      class="fixed inset-y-0 left-0 z-20 hidden w-64 flex-col border-r border-slate-200 bg-white lg:flex"
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
              :aria-expanded="menuOpen"
              @click="openMenu"
            >
              <AppIcon name="menu" />
            </button>
            <div>
              <div class="text-[11px] font-medium uppercase tracking-wider text-slate-500">
                {{ dateTime(now) }} · Berlin
              </div>
              <h1 class="text-base font-semibold">{{ heading }}</h1>
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-3">
            <label v-if="route.path === '/'" class="text-sm"
              ><span class="sr-only">Zeitraum</span
              ><select
                :value="dashboard.period"
                class="input"
                aria-label="Zeitraum"
                @change="
                  dashboard.setPeriod(
                    periodSchema.parse(($event.target as HTMLSelectElement).value),
                    $adminApi,
                  )
                "
              >
                <option value="today">Heute</option>
                <option value="24h">Letzte 24 Stunden</option>
                <option value="7d">Letzte 7 Tage</option>
              </select></label
            >
            <button
              disabled
              class="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white opacity-60"
              title="Datensatz anlegen ist noch nicht verfügbar"
            >
              + Datensatz<span class="block text-[10px] font-normal">Noch nicht verfügbar</span>
            </button>
          </div>
        </div>
      </header>
      <main id="main-content" tabindex="-1" class="mx-auto max-w-7xl space-y-5 p-5 sm:p-8">
        <LoginPanel @changed="accessChanged" /><AccessPanel @changed="accessChanged" /><slot />
      </main>
    </div>
  </div>
</template>
