<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import AppModal from './AppModal.vue'
import type AppIcon from './AppIcon.vue'
import type { GlobalSearchResponse } from '#shared/contracts'
import { adminNavigationItems } from '~/utils/navigation'
import { entityTypes } from '~/utils/entityPresentation'

const { $adminApi } = useNuxtApp()
const auth = useAuthStore()
const route = useRoute()
const modal = ref<InstanceType<typeof AppModal> | null>(null)
const input = ref<HTMLInputElement | null>(null)
const open = ref(false)
const query = ref('')
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
const sections = computed<{ key: string; label: string; items: PaletteItem[] }[]>(() => {
  const term = query.value.trim().toLocaleLowerCase('de')
  const navigation = adminNavigationItems.filter((item) =>
    `${item.label} ${'keywords' in item ? item.keywords : ''}`
      .toLocaleLowerCase('de')
      .includes(term),
  )
  let index = 0
  return [
    {
      key: 'navigation',
      label: 'Navigation',
      items: navigation.map((item) => ({
        key: item.to,
        label: item.label,
        subtitle: null,
        href: item.to,
        icon: item.icon,
        index: index++,
      })),
    },
    ...groups.value.map((group) => ({
      key: group.entity_type,
      label: entityTypes[group.entity_type].plural,
      items: group.items.map((item) => ({
        key: item.entity_key,
        label: item.label,
        subtitle: item.subtitle || entityTypes[item.entity_type].label,
        href: item.action.href,
        icon: entityTypes[item.entity_type].icon,
        index: index++,
      })),
    })),
  ].filter((section) => section.items.length)
})
const items = computed(() => sections.value.flatMap((section) => section.items))
const activeId = computed(() =>
  items.value[active.value] ? `${id}-option-${active.value}` : undefined,
)

function cancel() {
  generation++
  clearTimeout(timer)
  controller?.abort()
  controller = undefined
  loading.value = false
}
function reset() {
  cancel()
  open.value = false
  query.value = ''
  groups.value = []
  error.value = false
  active.value = 0
}
function close() {
  modal.value?.close()
  reset()
}
async function show() {
  if (open.value || !auth.isAdmin || auth.loggingOut) return
  open.value = true
  await modal.value?.open()
  input.value?.focus()
}
function schedule() {
  cancel()
  groups.value = []
  error.value = false
  active.value = 0
  const q = query.value.trim()
  if (!open.value || q.length < 2 || q.length > 120) return
  loading.value = true
  const request = generation
  controller = new AbortController()
  const signal = controller.signal
  timer = setTimeout(async () => {
    try {
      const data = await $adminApi.globalSearch({ q }, signal)
      if (request === generation && data.query === q) groups.value = data.groups
    } catch {
      if (request === generation) error.value = true
    } finally {
      if (request === generation) loading.value = false
    }
  }, 250)
}
watch(query, schedule, { flush: 'sync' })
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
  cancel()
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
    @close="reset"
  >
    <div class="flex min-h-0 flex-col">
      <div class="sticky top-0 z-10 border-b border-slate-100 bg-white px-4 pb-4 pt-3">
        <label :for="`${id}-input`" class="sr-only">Kulturbytes durchsuchen</label>
        <input
          :id="`${id}-input`"
          ref="input"
          v-model="query"
          type="search"
          class="input min-h-11 w-full"
          placeholder="Name, E-Mail oder UUID …"
          maxlength="120"
          autocomplete="off"
          autocapitalize="off"
          :spellcheck="false"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded="true"
          :aria-controls="`${id}-results`"
          :aria-activedescendant="activeId"
          @keydown="keydown"
        />
        <p class="mt-2 text-xs text-slate-500">Systemweit · unabhängig vom gewählten Gebiet</p>
      </div>
      <div class="search-results min-h-0 overflow-y-auto overflow-x-hidden px-2 pb-4">
        <p v-if="loading" role="status" class="p-3 text-sm text-slate-500">Suche läuft …</p>
        <p v-else-if="error" role="status" class="p-3 text-sm text-slate-500">
          Suche konnte nicht geladen werden.
        </p>
        <p v-else-if="!items.length" role="status" class="p-3 text-sm text-slate-500">
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
  overflow: hidden;
}
.search-palette :deep(button) {
  min-height: 44px;
  min-width: 44px;
}
.search-results {
  max-height: 55dvh;
}
@media (max-width: 639px) {
  .search-palette {
    width: calc(100vw - 1rem);
    max-height: calc(100dvh - 1rem);
    padding-bottom: env(safe-area-inset-bottom);
  }
  .search-results {
    height: 65dvh;
    max-height: calc(100dvh - 14rem - env(safe-area-inset-bottom));
  }
}
</style>
