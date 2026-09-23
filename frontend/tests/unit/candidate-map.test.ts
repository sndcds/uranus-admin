import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import CandidateMap from '../../app/components/CandidateMap.vue'
import InlineAlert from '../../app/components/InlineAlert.vue'
import OsmAttribution from '../../app/components/OsmAttribution.vue'
import { geocodeDetail } from '../fixtures/geocoding'
import { mapAttributionUrl, mapTileUrl } from '../../app/utils/map-tiles'

const state = vi.hoisted(() => ({
  container: undefined as HTMLElement | undefined,
  handlers: {} as Record<string, () => void>,
  fitBounds: vi.fn(),
  setView: vi.fn(),
  remove: vi.fn(),
  tileRemove: vi.fn(),
  invalidateSize: vi.fn(),
  disconnect: vi.fn(),
  resize: () => {},
  fail: false,
  markers: [] as { position: number[]; setZIndexOffset: ReturnType<typeof vi.fn> }[],
}))
vi.mock('leaflet', () => ({
  map: (container: HTMLElement) => {
    if (state.fail) throw new Error('Map unavailable')
    state.container = container
    return {
      fitBounds: state.fitBounds,
      setView: state.setView,
      remove: state.remove,
      invalidateSize: state.invalidateSize,
    }
  },
  latLngBounds: (positions: number[][]) => positions,
  control: { zoom: () => ({ addTo: vi.fn() }) },
  divIcon: (options: { html: HTMLElement }) => options,
  marker: (position: number[], { icon }: { icon: { html: HTMLElement } }) => {
    const marker = {
      position,
      setZIndexOffset: vi.fn(),
      remove: () => icon.html.remove(),
      addTo: () => {
        state.container?.append(icon.html)
        return marker
      },
    }
    state.markers.push(marker)
    return marker
  },
  tileLayer: () => ({
    on: (name: string, handler: () => void) => {
      state.handlers[name] = handler
    },
    off: vi.fn(),
    remove: state.tileRemove,
    addTo: vi.fn(),
  }),
}))
const candidate = geocodeDetail.candidates[0]!
const second = {
  ...candidate,
  id: 'second',
  rank: 2,
  latitude: 53.57,
  longitude: 9.88,
  display_name: '<img src=x onerror=alert(1)>',
}
let config: { mapTileUrl: string; mapTileAttribution: string; mapTileAttributionUrl: string }
const views: ReturnType<typeof mount>[] = []
function render(candidates = [candidate, second], selectedId = candidate.id) {
  const view = mount(CandidateMap, {
    props: { candidates, selectedId },
    global: { components: { InlineAlert, OsmAttribution } },
  })
  views.push(view)
  return view
}
beforeEach(() => {
  vi.clearAllMocks()
  state.handlers = {}
  state.markers = []
  state.fail = false
  config = {
    mapTileUrl: '/tiles/{z}/{x}/{y}.png',
    mapTileAttribution: 'Test provider',
    mapTileAttributionUrl: 'https://tiles.example.test/about',
  }
  vi.stubGlobal('useRuntimeConfig', () => ({ public: config }))
  vi.stubGlobal(
    'ResizeObserver',
    class {
      constructor(callback: () => void) {
        state.resize = callback
      }
      observe() {}
      disconnect = state.disconnect
    },
  )
})
afterEach(() => {
  views.splice(0).forEach((v) => v.unmount())
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('candidate map', () => {
  it('fits all geographic positions, ranks and selected marker, escaping provider text', async () => {
    const view = render()
    await flushPromises()
    expect(state.markers.map((m) => m.position)).toEqual([
      [candidate.latitude, candidate.longitude],
      [second.latitude, second.longitude],
    ])
    expect(state.fitBounds).toHaveBeenCalledWith(expect.anything(), {
      padding: [48, 48],
      maxZoom: 16,
      animate: false,
    })
    expect(view.findAll('.candidate-map-marker').map((m) => m.text())).toEqual(['1', '2'])
    expect(view.get('.candidate-map-marker[aria-pressed="true"]').text()).toBe('1')
    expect(state.markers[0]!.setZIndexOffset).toHaveBeenCalledWith(1000)
    expect(view.findAll('img')).toHaveLength(0)
    expect(view.get('a[href="https://www.openstreetmap.org/copyright"]').text()).toContain(
      'OpenStreetMap',
    )
    state.handlers.load!()
    await flushPromises()
    expect(view.text()).not.toContain('Karte wird geladen')
  })
  it('emits marker selection and follows selection changes; repeated focus recenters', async () => {
    const view = render()
    await flushPromises()
    await view.findAll('.candidate-map-marker')[1]!.trigger('click')
    expect(view.emitted('select')).toEqual([['second']])
    await view.setProps({ selectedId: 'second' })
    expect(state.setView).toHaveBeenLastCalledWith([second.latitude, second.longitude], 16, {
      animate: false,
    })
    expect(view.get('.candidate-map-marker[aria-pressed="true"]').text()).toBe('2')
    view.vm.focusCandidate('second')
    expect(state.setView).toHaveBeenCalledTimes(2)
    await view.get('button.button').trigger('click')
    expect(state.fitBounds).toHaveBeenCalledTimes(2)
  })
  it('caps a single point at street zoom and rebuilds changed candidates', async () => {
    const view = render([candidate])
    await flushPromises()
    expect(state.fitBounds).toHaveBeenCalledWith(
      [[candidate.latitude, candidate.longitude]],
      expect.objectContaining({ maxZoom: 16 }),
    )
    await view.setProps({ candidates: [second] })
    expect(view.findAll('.candidate-map-marker')).toHaveLength(1)
    expect(view.get('.candidate-map-marker').text()).toBe('2')
  })
  it('handles empty candidates without loading tiles', async () => {
    const view = render([])
    await flushPromises()
    expect(view.text()).toContain('Keine Standortkandidaten')
    expect(state.fitBounds).not.toHaveBeenCalled()
  })
  it.each(['', 'https://evil.test/{z}/{x}/{y}.png?name=private'])(
    'does not load missing/invalid configuration: %s',
    async (url) => {
      config.mapTileUrl = url
      const view = render()
      await flushPromises()
      expect(view.text()).toContain('Karte konnte nicht geladen werden')
      expect(state.fitBounds).not.toHaveBeenCalled()
    },
  )
  it('falls back on initialization failure', async () => {
    state.fail = true
    const view = render()
    await flushPromises()
    expect(view.get('[role="alert"]').text()).toContain('weiterhin in der Liste geprüft')
  })
  it('stops tile loading on error without retrying', async () => {
    const view = render()
    await flushPromises()
    state.handlers.tileerror!()
    await flushPromises()
    expect(state.tileRemove).toHaveBeenCalledOnce()
    expect(view.get('[role="alert"]').text()).toContain('Karte konnte nicht geladen werden')
  })
  it('times out hanging tiles and cleans up timers/map/resize on unmount', async () => {
    vi.useFakeTimers()
    const view = render()
    await flushPromises()
    state.resize()
    expect(state.invalidateSize).toHaveBeenCalledWith({ pan: false })
    await vi.advanceTimersByTimeAsync(12000)
    expect(view.text()).toContain('Karte konnte nicht geladen werden')
    view.unmount()
    expect(state.remove).toHaveBeenCalledOnce()
    expect(state.disconnect).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
  })
})
it('accepts only fixed XYZ paths, never credentials, query data or arbitrary placeholders', () => {
  expect(mapTileUrl('https://tiles.example.test/osm/{z}/{x}/{y}.png')).toBeTruthy()
  for (const url of [
    '//evil.test/{z}/{x}/{y}.png',
    'http://evil.test/{z}/{x}/{y}.png',
    'https://user:secret@evil.test/{z}/{x}/{y}.png',
    'https://{s}.test/{z}/{x}/{y}.png',
    '/tiles/{z}/{x}/{y}.png#data',
    '/tiles/{z}/{x}/{name}.png',
  ])
    expect(mapTileUrl(url)).toBeNull()
  expect(mapAttributionUrl('javascript:alert(1)')).toBeNull()
  expect(mapAttributionUrl('https://user:secret@tiles.test')).toBeNull()
})
