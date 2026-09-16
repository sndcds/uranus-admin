import { vi } from 'vitest'

export function mockFullscreen(supported = true) {
  let element: Element | null = null
  const original = [
    [document, 'fullscreenEnabled'],
    [document, 'fullscreenElement'],
    [document, 'exitFullscreen'],
    [HTMLElement.prototype, 'requestFullscreen'],
  ] as const
  const descriptors = original.map(([target, key]) => Object.getOwnPropertyDescriptor(target, key))
  function change(next: Element | null) {
    element = next
    document.dispatchEvent(new Event('fullscreenchange'))
  }
  const enter = vi.fn(function (this: HTMLElement) {
    change(this)
    return Promise.resolve()
  })
  const exit = vi.fn(() => {
    change(null)
    return Promise.resolve()
  })
  Object.defineProperty(document, 'fullscreenEnabled', { configurable: true, get: () => supported })
  Object.defineProperty(document, 'fullscreenElement', { configurable: true, get: () => element })
  Object.defineProperty(document, 'exitFullscreen', { configurable: true, value: exit })
  Object.defineProperty(HTMLElement.prototype, 'requestFullscreen', {
    configurable: true,
    value: enter,
  })
  return {
    enter,
    exit,
    change,
    restore() {
      original.forEach(([target, key], i) => {
        const descriptor = descriptors[i]
        if (descriptor) Object.defineProperty(target, key, descriptor)
        else Reflect.deleteProperty(target, key)
      })
    },
  }
}
