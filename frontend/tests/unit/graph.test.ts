import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { graphFixture } from '../fixtures/graph'
import { graphDataToSimulation, filterGraph, graphHref } from '../../app/utils/graph'
import {
  graphResponseSchema,
  graphNodeSchema,
  graphSearchResponseSchema,
} from '../../shared/contracts'
import EntityGraph from '../../app/components/EntityGraph.vue'
import GraphNodeDetails from '../../app/components/GraphNodeDetails.vue'
import GraphFilters from '../../app/components/GraphFilters.vue'
import { forwardAdminRequest } from '../../server/utils/admin-proxy'
const root = graphFixture.nodes[0]!

describe('relationship explorer', () => {
  it('isolates mutable D3 data and keeps only valid filtered endpoints', () => {
    const data = graphDataToSimulation(graphFixture.nodes, graphFixture.edges, root.id)
    data.nodes[0]!.label = 'changed'
    data.links[0]!.source = data.nodes[0]!
    expect(graphFixture.nodes[0]!.label).toBe(root.label)
    expect(typeof graphFixture.edges[0]!.source).toBe('string')
    const filtered = filterGraph(graphFixture.nodes, graphFixture.edges, 'venue', '', root.id)
    expect(filtered.nodes).toHaveLength(3)
    expect(filtered.edges).toHaveLength(2)
    expect(graphHref('image', root.key)).toBeNull()
    expect(graphHref('organization', root.key)).toContain('/graph?')
    expect(graphHref('user', 'bad')).toBeNull()
  })
  it('validates identities, endpoints and trusted link targets', () => {
    expect(graphResponseSchema.safeParse(graphFixture).success).toBe(true)
    expect(graphNodeSchema.safeParse({ ...root, admin_url: '//evil.test' }).success).toBe(false)
    expect(graphNodeSchema.safeParse({ ...root, public_url: 'javascript:alert(1)' }).success).toBe(
      false,
    )
    expect(graphResponseSchema.safeParse({ ...graphFixture, nodes: [root] }).success).toBe(false)
  })
  it.each([
    ['organization', 'organizations'],
    ['venue', 'venues'],
    ['space', 'spaces'],
    ['event', 'events'],
    ['user', 'users'],
  ])('accepts canonical %s targets in search and graph responses', (type, section) => {
    const key = '019e0000-0000-7000-8000-000000000001'
    const node = { ...root, id: `${type}:${key}`, type, key, admin_url: `/${section}/${key}` }
    expect(graphSearchResponseSchema.safeParse({ items: [node] }).success).toBe(true)
    expect(
      graphResponseSchema.safeParse({
        ...graphFixture,
        root: { type, key },
        nodes: [node],
        edges: [],
      }).success,
    ).toBe(true)
    expect(
      graphNodeSchema.safeParse({
        ...node,
        admin_url: `/activity?entity_key=${key}&entity_type=${type}`,
      }).success,
    ).toBe(true)
    expect(graphNodeSchema.safeParse({ ...node, admin_url: null }).success).toBe(true)
  })
  it('rejects unrelated, manipulated and external graph targets', () => {
    const user = graphFixture.nodes[1]!
    for (const admin_url of [
      `/events/${user.key}`,
      `/users/${root.key}`,
      `/users/${user.key}?redirect=https://evil.test`,
      `/users/${user.key}/edit`,
      `/users/../${user.key}`,
      `https://evil.test/users/${user.key}`,
      `//evil.test/users/${user.key}`,
      'javascript:alert(1)',
      `/activity?entity_key=${user.key}&entity_type=event`,
    ]) {
      expect(graphSearchResponseSchema.safeParse({ items: [{ ...user, admin_url }] }).success).toBe(
        false,
      )
    }
    expect(graphNodeSchema.safeParse({ ...user, id: root.id }).success).toBe(false)
  })
  it('renders keyboard-selectable nodes and stops its simulation on unmount', async () => {
    const wrapper = mount(EntityGraph, {
      props: {
        nodes: graphFixture.nodes,
        edges: graphFixture.edges,
        root: root.id,
        selected: root.id,
        depth: 2,
        showLabels: true,
      },
    })
    await nextTick()
    expect(wrapper.findAll('.graph-node')).toHaveLength(12)
    expect(wrapper.findAll('line')).toHaveLength(12)
    await wrapper.get('.graph-node').trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('select')?.[0]).toEqual([root.id])
    expect(wrapper.get('.graph-node').attributes('aria-pressed')).toBe('true')
    expect(wrapper.findAll('.graph-node').at(-1)?.attributes('opacity')).toBe('0.65')
    wrapper.unmount()
  })
  it('shows direct relationships and selects a neighbor outside the SVG', async () => {
    const wrapper = mount(GraphNodeDetails, {
      props: { node: root, nodes: graphFixture.nodes, edges: graphFixture.edges, root: root.id },
      global: { stubs: { NuxtLink: true } },
    })
    expect(wrapper.text()).toContain(root.key)
    expect(wrapper.text()).toContain('Beziehungen (6)')
    await wrapper.get('li button').trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual([graphFixture.nodes[1]!.id])
    expect(wrapper.find('a[target="_blank"]').exists()).toBe(false)
  })
  it('emits search, filter, depth and apply changes', async () => {
    const wrapper = mount(GraphFilters, {
      props: {
        query: '',
        entityType: '',
        relationType: '',
        organization: '',
        depth: 2,
        results: [root],
        searching: false,
        searched: true,
        organizations: [root],
        loading: false,
        hasRoot: true,
      },
      global: { stubs: { AppIcon: true } },
    })
    await nextTick()
    await wrapper.get('input').setValue('Rendsburg')
    expect(wrapper.emitted('update:query')?.[0]).toEqual(['Rendsburg'])
    await wrapper.get('[aria-label="Entitätstypen"]').setValue('venue')
    expect(wrapper.emitted('update:entityType')?.[0]).toEqual(['venue'])
    await wrapper.get('[aria-label="Beziehungstypen"]').setValue('venue_has_space')
    expect(wrapper.emitted('update:relationType')?.[0]).toEqual(['venue_has_space'])
    await wrapper.get('[aria-label="Maximale Tiefe"]').setValue('3')
    expect(wrapper.emitted('update:depth')?.[0]).toEqual([3])
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('apply')).toHaveLength(1)
  })
  it('allows only the two exact graph proxy routes and query keys', async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify(graphFixture)))
    const input = {
      path: '/api/v1/graph',
      method: 'GET',
      query: new URLSearchParams({ root_type: 'organization', root_key: root.key }),
      authorization: 'Bearer test',
    }
    expect((await forwardAdminRequest(input, 'http://localhost:8000', fetcher)).status).toBe(200)
    expect(
      (
        await forwardAdminRequest(
          { ...input, path: '/api/v1/graph/sql' },
          'http://localhost:8000',
          fetcher,
        )
      ).status,
    ).toBe(404)
    expect(
      (
        await forwardAdminRequest(
          { ...input, query: new URLSearchParams('sql=SELECT') },
          'http://localhost:8000',
          fetcher,
        )
      ).status,
    ).toBe(422)
    expect(
      (await forwardAdminRequest({ ...input, method: 'POST' }, 'http://localhost:8000', fetcher))
        .status,
    ).toBe(405)
  })
})
