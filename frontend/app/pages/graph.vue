<script setup lang="ts">
import type { GraphNode, GraphResponse } from '#shared/contracts'
import { graphEntityTypeSchema, graphRelationTypeSchema } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import type { ApiFailure } from '#shared/errors'
import { filterGraph } from '~/utils/graph'
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
    <p v-if="searchError" role="alert" class="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
      Suche fehlgeschlagen: {{ searchError.message }}
    </p>
    <GraphWorkspace
      :data="data"
      :nodes="visible.nodes"
      :edges="visible.edges"
      :root="root"
      :selected="selected"
      :depth="Number(route.query.depth || 2)"
      :show-labels="showLabels"
      :loading="loading"
      :error="error"
      @select="selected = $event"
      @root="choose"
      @retry="load"
    />
  </section>
</template>
