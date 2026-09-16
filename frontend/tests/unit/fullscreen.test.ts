import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { useFullscreen } from '../../app/composables/useFullscreen'
import { mockFullscreen } from '../fixtures/fullscreen'

let api: ReturnType<typeof mockFullscreen>
let wrapper: ReturnType<typeof mount>
let state: ReturnType<typeof useFullscreen>
const Harness = defineComponent({
  setup() {
    const target = ref<HTMLElement | null>(null)
    state = useFullscreen(target)
    return () =>
      h('div', { ref: target }, [h('button', { onClick: state.toggleFullscreen }, 'Fullscreen')])
  },
})
afterEach(() => {
  wrapper?.unmount()
  api?.restore()
  vi.restoreAllMocks()
})
describe('native fullscreen', () => {
  it('does not access browser APIs during SSR', async () => {
    const getter = vi.spyOn(globalThis, 'document', 'get').mockImplementation(() => {
      throw new Error('SSR document access')
    })
    expect(await renderToString(h(Harness))).toContain('Fullscreen')
    getter.mockRestore()
  })
  it('detects unsupported browsers', () => {
    api = mockFullscreen(false)
    wrapper = mount(Harness)
    expect(state.isSupported.value).toBe(false)
    void state.enterFullscreen()
    expect(api.enter).not.toHaveBeenCalled()
  })
  it('detects a missing element API even when the document enables fullscreen', () => {
    api = mockFullscreen()
    Reflect.deleteProperty(HTMLElement.prototype, 'requestFullscreen')
    wrapper = mount(Harness)
    expect(state.isSupported.value).toBe(false)
  })
  it('enters/exits its own target and restores focus after browser Escape', async () => {
    api = mockFullscreen()
    wrapper = mount(Harness, { attachTo: document.body })
    const button = wrapper.get('button')
    button.element.focus()
    await button.trigger('click')
    expect(api.enter).toHaveBeenCalledOnce()
    expect(document.fullscreenElement).toBe(wrapper.element)
    expect(state.isFullscreen.value).toBe(true)
    await state.exitFullscreen()
    expect(api.exit).toHaveBeenCalledOnce()
    expect(state.isFullscreen.value).toBe(false)
    await state.enterFullscreen()
    button.element.blur()
    api.change(null) // Browser-owned Escape, not a custom key handler.
    expect(state.isFullscreen.value).toBe(false)
    expect(document.activeElement).toBe(button.element)
  })
  it('ignores another fullscreen target and removes its listener on unmount', async () => {
    api = mockFullscreen()
    const remove = vi.spyOn(document, 'removeEventListener')
    wrapper = mount(Harness)
    api.change(document.createElement('div'))
    expect(state.isFullscreen.value).toBe(false)
    await state.exitFullscreen()
    expect(api.exit).not.toHaveBeenCalled()
    wrapper.unmount()
    expect(remove).toHaveBeenCalledWith('fullscreenchange', expect.any(Function))
    expect(api.exit).not.toHaveBeenCalled()
  })
  it('exits its own fullscreen when the workspace is removed', async () => {
    api = mockFullscreen()
    wrapper = mount(Harness)
    await state.enterFullscreen()
    wrapper.unmount()
    expect(api.exit).toHaveBeenCalledOnce()
  })
  it('sanitizes rejected browser requests without claiming fullscreen', async () => {
    api = mockFullscreen()
    api.enter.mockRejectedValueOnce(new Error('private browser detail'))
    wrapper = mount(Harness)
    await state.enterFullscreen()
    await flushPromises()
    expect(state.isFullscreen.value).toBe(false)
    expect(state.error.value).toBe('Vollbild konnte nicht aktiviert werden.')
    await state.enterFullscreen()
    api.exit.mockRejectedValueOnce(new Error('private exit detail'))
    await state.exitFullscreen()
    expect(state.error.value).not.toContain('private')
    expect(state.isFullscreen.value).toBe(true)
  })
})
