<script setup lang="ts">
import type { GraphNode, GraphResponse } from '#shared/contracts'
import { graphEntityTypeSchema, graphRelationTypeSchema } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import type { ApiFailure } from '#shared/errors'
import { filterGraph, nodePresentation } from '~/utils/graph'
const route = useRoute()
const router = useRouter()
const { $adminApi } = useNuxtApp()
const data = shallowRef<GraphResponse | null>(null)
const error = ref<ApiFailure | null>(null)
const searchError = ref<ApiFailure | null>(null)
const loading = ref(false)
const query = ref('')
const entityType = ref('')
const relationType = ref('')
const organization = ref('')
const depth = ref(2)
const selected = ref('')
const results = ref<GraphNode[]>([])
const searching = ref(false)
const searched = ref(false)
const showLabels = ref(true)
const settingsOpen = ref(false)
const root = computed(() => (data.value ? `${data.value.root.type}:${data.value.root.key}` : ''))
const organizations = computed(
  () => data.value?.nodes.filter((n) => n.type === 'organization') ?? [],
)
const visible = computed(() =>
  filterGraph(
    data.value?.nodes ?? [],
    data.value?.edges ?? [],
    typeof route.query.entity_type === 'string' ? route.query.entity_type : '',
    '',
    root.value,
  ),
)
const selectedNode = computed(() => visible.value.nodes.find((n) => n.id === selected.value))
let requestId = 0
let searchId = 0
let debounce: ReturnType<typeof setTimeout> | undefined
const stringParam = (key: string) =>
  typeof route.query[key] === 'string' ? (route.query[key] as string) : ''
async function load() {
  const id = ++requestId
  data.value = null
  selected.value = ''
  error.value = null
  loading.value = false
  entityType.value = stringParam('entity_type')
  relationType.value = stringParam('relation_type')
  depth.value = Number(stringParam('depth') || 2)
  if (!route.query.root_type && !route.query.root_key) return
  const type = graphEntityTypeSchema.safeParse(route.query.root_type)
  const key = stringParam('root_key')
  if (
    !type.success ||
    !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(key) ||
    ![1, 2, 3].includes(depth.value) ||
    (relationType.value && !graphRelationTypeSchema.safeParse(relationType.value).success) ||
    (entityType.value && !graphEntityTypeSchema.safeParse(entityType.value).success)
  ) {
    error.value = asFailure(new Error('Ungültiger Graph-Link'))
    return
  }
  loading.value = true
  try {
    const response = await $adminApi.graph({
      root_type: type.data,
      root_key: key,
      depth: depth.value,
      relation_type: relationType.value || undefined,
    })
    if (id !== requestId) return
    data.value = response
    selected.value = `${response.root.type}:${response.root.key}`
  } catch (cause) {
    if (id === requestId) error.value = asFailure(cause)
  } finally {
    if (id === requestId) loading.value = false
  }
}
async function choose(node: GraphNode) {
  query.value = ''
  results.value = []
  await router.push({
    path: '/graph',
    query: {
      root_type: node.type,
      root_key: node.key,
      depth: depth.value,
      entity_type: entityType.value || undefined,
      relation_type: relationType.value || undefined,
    },
  })
}
async function apply() {
  await router.push({
    query: {
      ...route.query,
      depth: depth.value,
      entity_type: entityType.value || undefined,
      relation_type: relationType.value || undefined,
    },
  })
}
async function reset() {
  query.value = ''
  organization.value = ''
  showLabels.value = true
  await router.push({
    query: route.query.root_key
      ? { root_type: stringParam('root_type'), root_key: stringParam('root_key'), depth: 2 }
      : {},
  })
  entityType.value = ''
  relationType.value = ''
  depth.value = 2
}
watch([query, entityType, organization], () => {
  const id = ++searchId
  clearTimeout(debounce)
  results.value = []
  searched.value = false
  searching.value = false
  searchError.value = null
  if (query.value.trim().length < 2) return
  searching.value = true
  debounce = setTimeout(async () => {
    try {
      const response = await $adminApi.graphSearch({
        q: query.value.trim(),
        entity_type: entityType.value || undefined,
        organization_id: organization.value || undefined,
      })
      if (id === searchId) {
        results.value = response.items
        searched.value = true
      }
    } catch (cause) {
      if (id === searchId) searchError.value = asFailure(cause)
    } finally {
      if (id === searchId) searching.value = false
    }
  }, 300)
})
onMounted(load)
watch(() => route.fullPath, load)
watch(
  useState('admin-access-revision', () => 0),
  () => {
    searchId++
    clearTimeout(debounce)
    results.value = []
    query.value = ''
    searching.value = false
    void load()
  },
)
onBeforeUnmount(() => {
  requestId++
  searchId++
  clearTimeout(debounce)
})
</script>
<template>
  <section class="space-y-3" aria-labelledby="graph-title">
    <header class="mb-5">
      <div class="flex items-center gap-3">
        <h2 id="graph-title" class="text-2xl font-bold tracking-tight">
          Entity-Relationship Graph
        </h2>
        <span class="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-semibold text-violet-700"
          >Beta</span
        >
      </div>
      <p class="mt-1 text-sm text-slate-500">
        Visualisiert die Zusammenhänge zwischen Organisationen, Orten, Räumen, Veranstaltungen,
        Terminen und Benutzern.
      </p>
    </header>
    <GraphFilters
      v-model:query="query"
      v-model:entity-type="entityType"
      v-model:relation-type="relationType"
      v-model:organization="organization"
      v-model:depth="depth"
      :results="results"
      :searching="searching"
      :searched="searched"
      :organizations="organizations"
      :loading="loading"
      :has-root="!!data"
      :settings-open="settingsOpen"
      @settings="settingsOpen = !settingsOpen"
      @select="choose"
      @apply="apply"
      @reset="reset"
    />
    <div v-if="settingsOpen" class="rounded-xl border border-slate-200 bg-white p-4 text-sm">
      <label class="flex items-center gap-2"
        ><input v-model="showLabels" type="checkbox" class="accent-fuchsia-600" />Beziehungen im
        Graph beschriften</label
      >
      <p class="mt-2 text-xs text-slate-500">
        Bei dichten Graphen erscheinen Beschriftungen nur an der Auswahl. Die Organisationsauswahl
        grenzt die Suche auf Organisationen im geladenen Graph ein. Knotenfilter behalten den
        Ausgangspunkt bei.
      </p>
    </div>
    <RequestState :loading="loading" :error="error" @retry="load" />
    <p v-if="searchError" role="alert" class="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
      Suche fehlgeschlagen: {{ searchError.message }}
    </p>
    <p
      v-if="data?.truncated"
      role="status"
      class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900"
    >
      Darstellung begrenzt: maximal {{ data.max_nodes }} Knoten und
      {{ data.max_edges }} Beziehungen. Wähle einen anderen Ausgangspunkt oder reduziere die Tiefe.
    </p>
    <div
      v-if="data"
      class="flex min-w-0 flex-col overflow-hidden rounded-xl border border-slate-200 xl:flex-row"
    >
      <EntityGraph
        :nodes="visible.nodes"
        :edges="visible.edges"
        :root="root"
        :selected="selected"
        :depth="Number(route.query.depth || 2)"
        :show-labels="showLabels"
        @select="selected = $event"
      />
      <GraphNodeDetails
        v-if="selectedNode"
        :node="selectedNode"
        :nodes="visible.nodes"
        :edges="visible.edges"
        :root="root"
        @close="selected = ''"
        @select="selected = $event"
        @root="choose"
      />
    </div>
    <div
      v-else-if="!loading && !error"
      class="grid min-h-[540px] place-items-center rounded-xl border border-slate-200 bg-white p-8 text-center"
    >
      <div class="max-w-md">
        <span
          class="mx-auto mb-5 grid h-20 w-20 place-items-center rounded-3xl bg-fuchsia-50 text-fuchsia-600"
          ><AppIcon name="graph" :size="36"
        /></span>
        <h3 class="text-lg font-semibold">Zusammenhänge entdecken</h3>
        <p class="mt-2 text-sm leading-6 text-slate-500">
          Suche nach einem Namen oder einer UUID und wähle einen Datensatz als Ausgangspunkt. Von
          dort erkundest du seine Orte, Veranstaltungen und weiteren Beziehungen.
        </p>
        <p class="mt-4 text-xs text-slate-400">Mindestens 2 Zeichen · Bis zu 3 Ebenen</p>
      </div>
    </div>
    <footer class="flex flex-wrap items-center justify-between gap-3">
      <ul
        aria-label="Graphlegende"
        class="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl bg-white px-3 py-2 text-[10px] text-slate-500"
      >
        <li v-for="item in nodePresentation" :key="item.label" class="flex items-center gap-1.5">
          <span
            class="grid h-5 w-5 place-items-center rounded-full"
            :style="{
              background: item.fill,
              color: item.color,
              border: `1px solid ${item.border}`,
            }"
            ><AppIcon :name="item.icon" :size="12" /></span
          >{{ item.label }}
        </li>
        <li class="flex items-center gap-1.5">
          <span class="w-6 border-t border-slate-400" />Beziehung
        </li>
        <li class="flex items-center gap-1.5">
          <span class="w-6 border-t border-violet-500" />Ausgewählt
        </li>
      </ul>
    </footer>
  </section>
</template>
