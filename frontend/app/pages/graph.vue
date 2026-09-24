<script setup lang="ts">
import { useFilterPreferencesStore } from '~/stores/filter-preferences'
import { usePreferenceQuery } from '~/composables/usePreferenceQuery'
import InlineAlert from '~/components/InlineAlert.vue'
import type { GraphNode, GraphResponse } from '#shared/contracts'
import { graphEntityTypeSchema, graphRelationTypeSchema } from '#shared/contracts'
import { asFailure } from '#shared/errors'
import type { ApiFailure } from '#shared/errors'
import { filterGraph } from '~/utils/graph'
import { nextTick } from 'vue'
const preferences = useFilterPreferencesStore()
const routeQuery = usePreferenceQuery(
  {
    entity_type: preferences.graph.entityType,
    relation_type: preferences.graph.relationType,
    depth: preferences.graph.depth,
  },
  (value) => preferences.hydrateGraph(value),
)
const router = useRouter()
const { $adminApi } = useNuxtApp()
const data = shallowRef<GraphResponse | null>(null)
const error = ref<ApiFailure | null>(null)
const searchError = ref<ApiFailure | null>(null)
const loading = ref(false)
const query = ref('')
const entityType = ref('')
const relationType = ref('')
const organization = computed({
  get: () => preferences.graph.organization,
  set: (value: string) => {
    preferences.graph.organization = value
  },
})
const depth = ref(2)
const selected = ref('')
const results = ref<GraphNode[]>([])
const searching = ref(false)
const searched = ref(false)
const showLabels = ref(true)
const settingsOpen = ref(false)
const geoScopeId = computed(() =>
  typeof routeQuery.value.geo_scope_id === 'string' ? routeQuery.value.geo_scope_id : undefined,
)
const root = computed(() => (data.value ? `${data.value.root.type}:${data.value.root.key}` : ''))
const organizations = computed(
  () => data.value?.nodes.filter((n) => n.type === 'organization') ?? [],
)
const visible = computed(() =>
  filterGraph(
    data.value?.nodes ?? [],
    data.value?.edges ?? [],
    typeof routeQuery.value.entity_type === 'string' ? routeQuery.value.entity_type : '',
    '',
    root.value,
  ),
)
const workspace = ref<{ focusRoot: () => void } | null>(null)
let loadedSelection = ''
let requestId = 0
let searchId = 0
let debounce: ReturnType<typeof setTimeout> | undefined
const stringParam = (key: string) =>
  typeof routeQuery.value[key] === 'string' ? (routeQuery.value[key] as string) : ''
async function load() {
  const id = ++requestId
  const selection = JSON.stringify([
    stringParam('root_type'),
    stringParam('root_key'),
    stringParam('depth') || '2',
    stringParam('entity_type'),
    stringParam('relation_type'),
    stringParam('geo_scope_id'),
  ])
  const retain = selection === loadedSelection
  if (!retain) {
    data.value = null
    selected.value = ''
  }
  error.value = null
  loading.value = false
  entityType.value = stringParam('entity_type')
  relationType.value = stringParam('relation_type')
  depth.value = Number(stringParam('depth') || 2)
  if (!routeQuery.value.root_type && !routeQuery.value.root_key) return
  const type = graphEntityTypeSchema.safeParse(routeQuery.value.root_type)
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
    loadedSelection = selection
    if (!retain || !response.nodes.some((node) => node.id === selected.value))
      selected.value = `${response.root.type}:${response.root.key}`
  } catch (cause) {
    if (id === requestId) {
      error.value = asFailure(cause)
      if ([401, 403, 404, 422].includes(error.value.status)) {
        data.value = null
        selected.value = ''
      }
    }
  } finally {
    if (id === requestId) {
      loading.value = false
      if (focusAfterSelection && data.value) {
        focusAfterSelection = false
        await nextTick()
        if (id === requestId) workspace.value?.focusRoot()
      }
    }
  }
}
function remember() {
  preferences.hydrateGraph({
    entity_type: entityType.value,
    relation_type: relationType.value,
    depth: depth.value,
  })
}
watch([entityType, relationType, depth], remember)
let focusAfterSelection = false
async function choose(node: GraphNode) {
  focusAfterSelection = true
  query.value = ''
  results.value = []
  await router.push({
    path: '/graph',
    query: {
      geo_scope_id: geoScopeId.value,
      root_type: node.type,
      root_key: node.key,
      depth: depth.value,
      entity_type: entityType.value || undefined,
      relation_type: relationType.value || undefined,
    },
  })
  // Selecting the current root can be a duplicate navigation (no load watcher).
  if (focusAfterSelection && !loading.value && root.value === node.id) {
    focusAfterSelection = false
    await nextTick()
    workspace.value?.focusRoot()
  }
}
async function apply() {
  if (
    depth.value === Number(stringParam('depth') || 2) &&
    entityType.value === stringParam('entity_type') &&
    relationType.value === stringParam('relation_type')
  ) {
    await load()
    return
  }
  await router.push({
    query: {
      ...routeQuery.value,
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
    query: routeQuery.value.root_key
      ? {
          root_type: stringParam('root_type'),
          root_key: stringParam('root_key'),
          depth: 2,
          geo_scope_id: geoScopeId.value,
        }
      : { geo_scope_id: geoScopeId.value },
  })
  entityType.value = ''
  relationType.value = ''
  depth.value = 2
  preferences.hydrateGraph({})
}
watch([query, entityType, organization, geoScopeId], () => {
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
        geo_scope_id: geoScopeId.value,
        entity_type:
          geoScopeId.value && entityType.value === 'user'
            ? undefined
            : entityType.value || undefined,
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
watch(() => routeQuery.value, load)
onBeforeUnmount(() => {
  requestId++
  searchId++
  clearTimeout(debounce)
})
</script>
<template>
  <section class="operations-page" aria-labelledby="graph-title">
    <PageHeader
      title="Beziehungsgraph"
      title-id="graph-title"
      description="Beziehungen zwischen Datensätzen untersuchen."
    >
      <template #badge><StatusBadge label="Beta" /></template>
    </PageHeader>
    <GraphFilters
      v-model:query="query"
      v-model:entity-type="entityType"
      v-model:relation-type="relationType"
      v-model:organization="organization"
      v-model:depth="depth"
      v-model:show-labels="showLabels"
      :geo-active="!!geoScopeId"
      :results="results"
      :searching="searching"
      :searched="searched"
      :organizations="organizations"
      :loading="loading"
      :has-root="!!routeQuery.root_key"
      :settings-open="settingsOpen"
      @settings="settingsOpen = !settingsOpen"
      @select="choose"
      @apply="apply"
      @reset="reset"
    />
    <InlineAlert v-if="searchError" tone="warning">
      Suche fehlgeschlagen: {{ searchError.message }}
    </InlineAlert>
    <GraphWorkspace
      ref="workspace"
      :entity-filter="stringParam('entity_type')"
      :relation-filter="stringParam('relation_type')"
      :geo-scope="geoScopeId"
      :data="data"
      :nodes="visible.nodes"
      :edges="visible.edges"
      :root="root"
      :selected="selected"
      :depth="Number(routeQuery.depth || 2)"
      :show-labels="showLabels"
      :loading="loading"
      :error="error"
      @select="selected = $event"
      @root="choose"
      @retry="load"
    />
  </section>
</template>
