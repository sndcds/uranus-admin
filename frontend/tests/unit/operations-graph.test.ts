import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, shallowMount } from '@vue/test-utils'
import * as vue from 'vue'
import Graph from '../../app/pages/graph.vue'
import GraphFilters from '../../app/components/GraphFilters.vue'
import GraphWorkspace from '../../app/components/GraphWorkspace.vue'
import { graphFixture } from '../fixtures/graph'
import { useFilterPreferencesStore } from '../../app/stores/filter-preferences'
import { AdminApiError, failure } from '../../shared/errors'
import type { GraphResponse } from '../../shared/contracts'

const root = graphFixture.nodes[0]!
const route = vue.reactive({ path: '/graph', query: {} as Record<string, string> })
const navigate = vi.fn(async ({ query }: { query: Record<string, unknown> }) => {
  route.query = Object.fromEntries(
    Object.entries(query)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => [k, String(v)]),
  )
})
const api = { graph: vi.fn(), graphSearch: vi.fn() }
let view: ReturnType<typeof shallowMount>
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}
const initial = () => ({ root_type: root.type, root_key: root.key, depth: '2' })
function mountPage() {
  view = shallowMount(Graph, {
    global: {
      components: { GraphFilters, GraphWorkspace },
      stubs: { PageHeader: true, StatusBadge: true, InlineAlert: false },
    },
  })
  Object.assign(view.getComponent(GraphWorkspace).vm, { focusRoot: vi.fn() })
  return view
}
const workspace = () => view.getComponent(GraphWorkspace)
const filters = () => view.getComponent(GraphFilters)
beforeEach(() => {
  setActivePinia(createPinia())
  route.query = initial()
  api.graph.mockReset().mockResolvedValue(graphFixture)
  api.graphSearch.mockReset().mockResolvedValue({ items: [root] })
  navigate.mockClear()
  for (const key of [
    'ref',
    'shallowRef',
    'computed',
    'watch',
    'onMounted',
    'onBeforeUnmount',
  ] as const)
    vi.stubGlobal(key, vue[key])
  vi.stubGlobal('useRoute', () => route)
  vi.stubGlobal('useRouter', () => ({ push: navigate, replace: navigate }))
  vi.stubGlobal('useNuxtApp', () => ({ $adminApi: api }))
})
afterEach(() => {
  view?.unmount()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('graph operations workspace requests', () => {
  it('has no synthetic graph without a root', async () => {
    route.query = {}
    mountPage()
    await flushPromises()
    expect(api.graph).not.toHaveBeenCalled()
    expect(workspace().props('data')).toBeNull()
    expect(workspace().props('error')).toBeNull()
  })
  it('retains the same selection and inspector on refresh, with explicit stale errors', async () => {
    mountPage()
    await flushPromises()
    workspace().vm.$emit('select', graphFixture.nodes[1]!.id)
    const pending = deferred<GraphResponse>()
    api.graph.mockReturnValueOnce(pending.promise)
    workspace().vm.$emit('retry')
    await flushPromises()
    expect(workspace().props('loading')).toBe(true)
    expect(workspace().props('data')).toEqual(graphFixture)
    pending.reject(new AdminApiError(failure(503)))
    await flushPromises()
    expect(workspace().props('data')).toEqual(graphFixture)
    expect(workspace().props('error').status).toBe(503)
    filters().vm.$emit('apply')
    await flushPromises()
    expect(workspace().props('selected')).toBe(graphFixture.nodes[1]!.id)
    expect(workspace().props('error')).toBeNull()
  })
  it.each([401, 403, 404, 422])('clears retained graph on %s', async (status) => {
    mountPage()
    await flushPromises()
    api.graph.mockRejectedValueOnce(new AdminApiError(failure(status)))
    workspace().vm.$emit('retry')
    await flushPromises()
    expect(workspace().props('data')).toBeNull()
    expect(workspace().props('selected')).toBe('')
    expect(workspace().props('error').status).toBe(status)
  })
  it.each(['depth', 'entity_type', 'relation_type', 'root_key'])(
    'clears graph for a changed %s and ignores late responses',
    async (key) => {
      mountPage()
      await flushPromises()
      const stale = deferred<GraphResponse>()
      api.graph.mockReturnValueOnce(stale.promise)
      workspace().vm.$emit('retry')
      await flushPromises()
      const current = deferred<GraphResponse>()
      api.graph.mockReturnValueOnce(current.promise)
      route.query = {
        ...initial(),
        [key]: {
          depth: '3',
          entity_type: 'venue',
          relation_type: 'organization_has_venue',
          root_key: graphFixture.nodes[1]!.key,
        }[key]!,
      }
      await flushPromises()
      expect(workspace().props('data')).toBeNull()
      stale.resolve(graphFixture)
      await flushPromises()
      expect(workspace().props('data')).toBeNull()
      const response = {
        ...graphFixture,
        nodes: graphFixture.nodes.map((n) => ({ ...n, label: 'Current' })),
      }
      current.resolve(response)
      await flushPromises()
      expect(workspace().props('data')).toEqual(response)
    },
  )
  it('invalid links and removing the root invalidate pending responses', async () => {
    const pending = deferred<GraphResponse>()
    api.graph.mockReturnValueOnce(pending.promise)
    mountPage()
    await flushPromises()
    route.query = { ...initial(), depth: '4' }
    await flushPromises()
    expect(workspace().props('error')).not.toBeNull()
    pending.resolve(graphFixture)
    await flushPromises()
    expect(workspace().props('data')).toBeNull()
    route.query = {}
    await flushPromises()
    expect(workspace().props('error')).toBeNull()
  })
  it('debounces server search, preserves geo/organization/type and discards late results/errors', async () => {
    vi.useFakeTimers()
    route.query = { ...initial(), geo_scope_id: root.key }
    mountPage()
    await flushPromises()
    filters().vm.$emit('update:entityType', 'venue')
    filters().vm.$emit('update:organization', root.key)
    filters().vm.$emit('update:query', '  Hafen  ')
    await vue.nextTick()
    await vi.advanceTimersByTimeAsync(299)
    expect(api.graphSearch).not.toHaveBeenCalled()
    const stale = deferred<{ items: typeof graphFixture.nodes }>()
    api.graphSearch.mockReturnValueOnce(stale.promise)
    await vi.advanceTimersByTimeAsync(1)
    expect(api.graphSearch).toHaveBeenLastCalledWith({
      q: 'Hafen',
      geo_scope_id: root.key,
      organization_id: root.key,
      entity_type: 'venue',
    })
    filters().vm.$emit('update:query', 'Saal')
    await vue.nextTick()
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()
    expect(filters().props('results')).toEqual([root])
    stale.reject(new AdminApiError(failure(503)))
    await flushPromises()
    expect(view.text()).not.toContain('Suche fehlgeschlagen')
    filters().vm.$emit('select', root)
    await flushPromises()
    expect(route.query.geo_scope_id).toBe(root.key)
    expect(api.graph.mock.lastCall?.[0]).not.toHaveProperty('geo_scope_id')
    expect(filters().props('query')).toBe('')
    expect(filters().props('results')).toEqual([])
  })
  it('reports current search errors and resets filters while retaining root and geo', async () => {
    vi.useFakeTimers()
    route.query = {
      ...initial(),
      geo_scope_id: root.key,
      entity_type: 'venue',
      relation_type: 'organization_has_venue',
      depth: '3',
    }
    mountPage()
    await flushPromises()
    api.graphSearch.mockRejectedValueOnce(new AdminApiError(failure(503)))
    filters().vm.$emit('update:query', 'test')
    await vue.nextTick()
    await vi.advanceTimersByTimeAsync(300)
    expect(view.text()).toContain('Suche fehlgeschlagen')
    filters().vm.$emit('update:organization', root.key)
    filters().vm.$emit('update:showLabels', false)
    filters().vm.$emit('settings')
    await vue.nextTick()
    expect(filters().props('settingsOpen')).toBe(true)
    filters().vm.$emit('reset')
    await flushPromises()
    expect(route.query).toEqual({ ...initial(), geo_scope_id: root.key })
    expect(filters().props('showLabels')).toBe(true)
    expect(useFilterPreferencesStore().graph.organization).toBe('')
    expect(filters().props('entityType')).toBe('')
  })
})
