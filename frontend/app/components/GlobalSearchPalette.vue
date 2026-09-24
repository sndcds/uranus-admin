<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import AppModal from './AppModal.vue'
import type AppIcon from './AppIcon.vue'
import type { GlobalSearchResponse } from '#shared/contracts'
import { adminNavigationItems } from '~/utils/navigation'
import { globalSearchTypes } from '~/utils/entityPresentation'

const { $adminApi } = useNuxtApp()
const auth = useAuthStore()
const route = useRoute()
const modal = ref<InstanceType<typeof AppModal> | null>(null)
const input = ref<HTMLInputElement | null>(null)
const open = ref(false)
const query = ref('')
const debouncedQuery = ref('')
const resultQuery = ref('')
const results = ref<HTMLElement | null>(null)
const groups = ref<GlobalSearchResponse['groups']>([])
const loading = ref(false)
const error = ref(false)
const active = ref(0)
const id = useId()
let generation = 0
let timer: ReturnType<typeof setTimeout> | undefined
let controller: AbortController | undefined

type PaletteItem = {
  key: string
  label: string
  subtitle: string | null
  href: string
  icon: InstanceType<typeof AppIcon>['$props']['name']
  index: number
}
// Navigation follows the input immediately; remote sections retain their last response.
const navigationResults = computed(() => {
  const term = query.value.trim().toLocaleLowerCase('de')
  return adminNavigationItems
    .filter((item) =>
      `${item.label} ${'keywords' in item ? item.keywords : ''}`
        .toLocaleLowerCase('de')
        .includes(term),
    )
    .map((item) => ({
      key: `navigation:${item.to}`,
      label: item.label,
      subtitle: null,
      href: item.to,
      icon: item.icon,
    }))
})
const remoteSections = computed(() =>
  groups.value.map((group) => ({
    key: group.entity_type,
    label: globalSearchTypes[group.entity_type].plural,
    items: group.items.map((item) => ({
      key: `${item.entity_type}:${item.entity_key}`,
      label: item.label,
      subtitle: item.subtitle || globalSearchTypes[item.entity_type].label,
      href: item.action.href,
      icon: globalSearchTypes[item.entity_type].icon,
    })),
  })),
)
const sections = computed<{ key: string; label: string; items: PaletteItem[] }[]>(() => {
  let index = 0
  return [
    { key: 'navigation', label: 'Navigation', items: navigationResults.value },
    ...remoteSections.value,
  ]
    .filter((section) => section.items.length)
    .map((section) => ({
      ...section,
      items: section.items.map((item) => ({ ...item, index: index++ })),
    }))
})
const items = computed(() => sections.value.flatMap((section) => section.items))
const activeId = computed(() =>
  items.value[active.value] ? `${id}-option-${active.value}` : undefined,
)

const resultsAreStale = computed(
  () => loading.value && !!resultQuery.value && resultQuery.value !== debouncedQuery.value,
)
const requestStatus = computed(() => {
  if (error.value) return 'Neue Suche konnte nicht geladen werden.'
  if (resultsAreStale.value) return 'Ergebnisse werden aktualisiert …'
  return loading.value ? 'Suche läuft …' : ''
})

// Preserve the selected identity when only local navigation changes its indices.
watch(
  items,
  (current, previous) => {
    const key = previous[active.value]?.key
    const index = current.findIndex((item) => item.key === key)
    active.value = index >= 0 ? index : 0
  },
  { flush: 'sync' },
)
function cancelPending() {
  generation++
  clearTimeout(timer)
  timer = undefined
  controller?.abort()
  controller = undefined
  loading.value = false
}
function clearResults() {
  groups.value = []
  resultQuery.value = ''
  debouncedQuery.value = ''
  error.value = false
}
function resetPalette() {
  cancelPending()
  open.value = false
  query.value = ''
  clearResults()
  active.value = 0
}
function close() {
  modal.value?.close()
  resetPalette()
}
async function show() {
  if (open.value || !auth.isAdmin || auth.loggingOut) return
  open.value = true
  await modal.value?.open()
  input.value?.focus()
}
async function performSearch(q: string, request: number) {
  if (request !== generation || !open.value || query.value.trim() !== q) return
  timer = undefined
  debouncedQuery.value = q
  loading.value = true
  error.value = false
  controller = new AbortController()
  try {
    const data = await $adminApi.globalSearch({ q }, controller.signal)
    if (request !== generation || query.value.trim() !== q || data.query !== q) return
    // Vue batches this successful snapshot into one render; cancellation never clears it.
    groups.value = data.groups
    resultQuery.value = data.query
    active.value = 0
    await nextTick()
    if (request === generation && results.value) results.value.scrollTop = 0
  } catch {
    if (request === generation) error.value = true
  } finally {
    if (request === generation) {
      loading.value = false
      controller = undefined
    }
  }
}
function scheduleSearch() {
  cancelPending()
  const q = query.value.trim()
  if (!open.value || q.length < 2) {
    clearResults()
    return
  }
  if (q.length > 120) return
  const request = generation
  timer = setTimeout(() => void performSearch(q, request), 250)
}
watch(query, scheduleSearch, { flush: 'sync' })
watch(() => [auth.isAdmin, auth.revision, auth.loggingOut], close, { flush: 'sync' })
watch(() => route.path, close)
async function select(href: string) {
  close()
  await navigateTo(href)
}
function keydown(event: KeyboardEvent) {
  if (event.isComposing) return
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    close()
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const item = items.value[active.value]
    if (item) void select(item.href)
  } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (!items.value.length) return
    active.value =
      (active.value + (event.key === 'ArrowDown' ? 1 : -1) + items.value.length) %
      items.value.length
    void nextTick(() =>
      document.getElementById(activeId.value || '')?.scrollIntoView?.({ block: 'nearest' }),
    )
  }
}
function shortcut(event: KeyboardEvent) {
  if (
    (event.ctrlKey || event.metaKey) &&
    !event.altKey &&
    !event.shiftKey &&
    event.key.toLowerCase() === 'k' &&
    !event.isComposing &&
    auth.isAdmin
  ) {
    event.preventDefault()
    event.stopPropagation()
    if (!event.repeat) void show()
  }
}
onMounted(() => document.addEventListener('keydown', shortcut, true))
onBeforeUnmount(() => {
  cancelPending()
  document.removeEventListener('keydown', shortcut, true)
})
defineExpose({ show })
</script>

<template>
  <AppModal
    ref="modal"
    title="Kulturbytes durchsuchen"
    workspace
    class="search-palette"
    @close="resetPalette"
  >
    <div class="flex min-h-0 flex-1 flex-col">
      <div class="search-header shrink-0 border-b border-slate-100 bg-white px-4 pb-3 pt-3">
        <label :for="`${id}-input`" class="sr-only">Kulturbytes durchsuchen</label>
        <div class="relative">
          <input
            :id="`${id}-input`"
            ref="input"
            v-model="query"
            type="search"
            class="input min-h-11 w-full pr-10"
            placeholder="Name, E-Mail, Titel oder UUID …"
            maxlength="120"
            autocomplete="off"
            autocapitalize="off"
            :spellcheck="false"
            role="combobox"
            aria-autocomplete="list"
            aria-expanded="true"
            :aria-controls="`${id}-results`"
            :aria-activedescendant="activeId"
            :aria-describedby="`${id}-result-query`"
            @keydown="keydown"
          />
          <span
            v-if="loading"
            aria-hidden="true"
            class="pointer-events-none absolute right-3 top-1/2 -mt-2 h-4 w-4 animate-spin rounded-full border-2 border-slate-200 border-t-fuchsia-700 motion-reduce:animate-none"
          />
        </div>
        <p class="mt-2 text-xs text-slate-500">Systemweit · unabhängig vom gewählten Gebiet</p>
        <div class="mt-1 h-10 text-xs leading-5 text-slate-500">
          <p class="h-5 truncate" role="status" aria-live="polite">{{ requestStatus }}</p>
          <p :id="`${id}-result-query`" class="h-5 truncate" :title="resultQuery">
            <template v-if="resultQuery">Datensätze für „{{ resultQuery }}“</template>
          </p>
        </div>
      </div>
      <div
        ref="results"
        class="search-results min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-2 pb-4"
      >
        <p
          v-if="!items.length && !loading && !error"
          role="status"
          class="p-3 text-sm text-slate-500"
        >
          Keine passenden Ergebnisse gefunden.
        </p>
        <div :id="`${id}-results`" role="listbox" aria-label="Suchergebnisse" :aria-busy="loading">
          <div
            v-for="section in sections"
            :key="section.key"
            role="group"
            :aria-labelledby="`${id}-${section.key}`"
          >
            <div
              :id="`${id}-${section.key}`"
              class="px-3 pb-1 pt-4 text-xs font-semibold text-slate-500"
            >
              {{ section.label }}
            </div>
            <div
              v-for="item in section.items"
              :id="`${id}-option-${item.index}`"
              :key="item.key"
              role="option"
              :aria-selected="active === item.index"
              class="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl p-3 hover:bg-fuchsia-50"
              :class="{ 'bg-fuchsia-50 ring-1 ring-inset ring-fuchsia-300': active === item.index }"
              @pointerdown.prevent
              @click="select(item.href)"
            >
              <AppIcon :name="item.icon" class="shrink-0" />
              <span class="min-w-0">
                <span class="block truncate text-sm font-semibold">{{ item.label }}</span>
                <span
                  v-if="item.subtitle"
                  class="block break-words text-xs text-slate-500 [overflow-wrap:anywhere]"
                  >{{ item.subtitle }}</span
                >
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </AppModal>
</template>

<style scoped>
.search-palette {
  height: min(38rem, calc(100dvh - 2rem));
  overflow: hidden;
}
/* Closed native dialogs must retain display:none. Other AppModal layouts are unchanged. */
.search-palette[open] {
  display: flex;
  flex-direction: column;
}
.search-palette :deep(> div:first-child) {
  flex-shrink: 0;
}
.search-palette :deep(button) {
  min-height: 44px;
  min-width: 44px;
}
.search-results {
  scrollbar-gutter: stable;
}
@media (max-width: 639px) {
  .search-palette {
    width: calc(100vw - 1rem);
    height: calc(100dvh - 1rem);
    max-height: calc(100dvh - 1rem);
    padding-top: env(safe-area-inset-top);
    padding-bottom: env(safe-area-inset-bottom);
  }
}
</style>
