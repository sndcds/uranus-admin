import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import * as forces from 'd3-force'
import GraphWorkspace from '../../app/components/GraphWorkspace.vue'
import EntityGraph from '../../app/components/EntityGraph.vue'
import { graphFixture } from '../fixtures/graph'
import { mockFullscreen } from '../fixtures/fullscreen'

vi.mock('d3-force', async (importOriginal) => {
  const actual = await importOriginal<typeof import('d3-force')>()
  return { ...actual, forceSimulation: vi.fn(actual.forceSimulation) }
})

const root = graphFixture.nodes[0]!
let api: ReturnType<typeof mockFullscreen>
let wrapper: ReturnType<typeof mount>
afterEach(async () => {
  wrapper?.unmount()
  await flushPromises()
  api?.restore()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})
function workspace() {
  return mount(GraphWorkspace, {
    props: {
      data: graphFixture,
      nodes: graphFixture.nodes,
      edges: graphFixture.edges,
      root: root.id,
      selected: root.id,
      depth: 2,
      showLabels: true,
      loading: false,
      error: null,
    },
    global: { stubs: { NuxtLink: true } },
  })
}
describe('fullscreen graph workspace', () => {
  it('uses one SVG, switches controls and toggles details without recreating nodes', async () => {
    api = mockFullscreen()
    const simulate = vi.mocked(forces.forceSimulation)
    simulate.mockClear()
    wrapper = workspace()
    await nextTick()
    await nextTick()
    const svg = wrapper.get('svg[role="group"]').element
    const node = wrapper.get('.graph-node').element
    await wrapper.get('[aria-label="Graph im Vollbild anzeigen"]').trigger('click')
    expect(document.fullscreenElement).toBe(wrapper.element)
    expect(wrapper.get('[aria-label="Vollbild beenden"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('svg[role="group"]').element).toBe(svg)
    expect(wrapper.get('.graph-node').element).toBe(node)
    expect(wrapper.findAllComponents(EntityGraph)).toHaveLength(1)
    expect(simulate).toHaveBeenCalledOnce()
    const details = wrapper.findAll('button').find((b) => b.text().includes('Details ausblenden'))!
    await details.trigger('click')
    expect(wrapper.find('[aria-label="Knotendetails"]').exists()).toBe(false)
    await wrapper.get('.graph-node').trigger('click')
    expect(wrapper.find('[aria-label="Knotendetails"]').exists()).toBe(true)
    await wrapper.get('[aria-label="Vollbild beenden"]').trigger('click')
    expect(api.exit).toHaveBeenCalledOnce()
    expect(wrapper.get('[aria-label="Graph im Vollbild anzeigen"]').exists()).toBe(true)
    await wrapper.get('[aria-label="Graph im Vollbild anzeigen"]').trigger('click')
    api.change(null)
    await nextTick()
    expect(wrapper.get('[aria-label="Graph im Vollbild anzeigen"]').exists()).toBe(true)
  })
  it('keeps the target and loading/errors/legend inside fullscreen during reload', async () => {
    api = mockFullscreen()
    wrapper = workspace()
    await nextTick()
    await wrapper.get('[aria-label="Graph im Vollbild anzeigen"]').trigger('click')
    const target = wrapper.element
    await wrapper.setProps({ data: null, nodes: [], edges: [], loading: true })
    expect(document.fullscreenElement).toBe(target)
    expect(wrapper.text()).toContain('Daten werden geladen')
    expect(wrapper.find('[aria-label="Graphlegende"]').exists()).toBe(true)
    expect(wrapper.get('[aria-label="Vollbild beenden"]').exists()).toBe(true)
    await wrapper.setProps({
      loading: false,
      error: { status: 503, code: 'unavailable', message: 'Nicht verfügbar' },
    })
    expect(wrapper.get('[role="alert"]').text()).toContain('Nicht verfügbar')
    await wrapper.setProps({
      data: { ...graphFixture, truncated: true },
      nodes: graphFixture.nodes,
      edges: graphFixture.edges,
      error: null,
    })
    expect(document.fullscreenElement).toBe(target)
    expect(wrapper.text()).toContain('Darstellung begrenzt')
  })
  it('hides unsupported controls and handles rejected entry', async () => {
    api = mockFullscreen(false)
    wrapper = workspace()
    await nextTick()
    expect(wrapper.find('[aria-label="Graph im Vollbild anzeigen"]').exists()).toBe(false)
    wrapper.unmount()
    api.restore()
    api = mockFullscreen()
    api.enter.mockRejectedValueOnce(new Error('private'))
    wrapper = workspace()
    await nextTick()
    await wrapper.get('[aria-label="Graph im Vollbild anzeigen"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Vollbild konnte nicht aktiviert werden.')
    expect(wrapper.text()).not.toContain('private')
  })
  it('updates dimensions with ResizeObserver and preserves manual zoom on ordinary resize', async () => {
    api = mockFullscreen()
    let resize: ResizeObserverCallback = () => {}
    const disconnect = vi.fn()
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(callback: ResizeObserverCallback) {
          resize = callback
        }
        observe() {}
        disconnect = disconnect
      },
    )
    const frames: FrameRequestCallback[] = []
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      frames.push(callback)
      return frames.length
    })
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
    wrapper = workspace()
    await nextTick()
    await nextTick()
    const measure = async (width: number, height: number) => {
      resize([{ contentRect: { width, height } } as ResizeObserverEntry], {} as ResizeObserver)
      await nextTick()
    }
    await measure(800, 600)
    const svg = wrapper.get('svg[role="group"]')
    await wrapper.get('[aria-label="Vergrößern"]').trigger('click')
    const transform = svg.get('g[transform]').attributes('transform')
    await measure(900, 650)
    expect(svg.attributes('viewBox')).toBe('0 0 900 650')
    expect(svg.get('g[transform]').attributes('transform')).toBe(transform)
    await wrapper.get('[aria-label="Graph im Vollbild anzeigen"]').trigger('click')
    await measure(1400, 900)
    frames.shift()?.(0)
    frames.shift()?.(0)
    await nextTick()
    expect(svg.attributes('viewBox')).toBe('0 0 1400 900')
    expect(svg.get('g[transform]').attributes('transform')).not.toBe(transform)
    wrapper.unmount()
    expect(disconnect).toHaveBeenCalledOnce()
  })
})
