import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Ref } from 'vue'

/** Browser state is authoritative; never fullscreen another feature's element. */
export function useFullscreen(target: Ref<HTMLElement | null>) {
  const isFullscreen = ref(false)
  const isSupported = ref(false)
  const error = ref('')
  let browser: Document | undefined
  let returnFocus: HTMLElement | null = null
  function sync() {
    const wasFullscreen = isFullscreen.value
    isSupported.value =
      !!browser?.fullscreenEnabled && typeof target.value?.requestFullscreen === 'function'
    isFullscreen.value = !!target.value && browser?.fullscreenElement === target.value
    if (wasFullscreen && !isFullscreen.value && returnFocus?.isConnected) {
      returnFocus.focus({ preventScroll: true })
    }
  }
  async function enterFullscreen() {
    if (!browser || !isSupported.value || !target.value) return
    error.value = ''
    returnFocus = browser.activeElement instanceof HTMLElement ? browser.activeElement : null
    try {
      // Invoke directly inside the click handler, before yielding the user gesture.
      await target.value.requestFullscreen()
      sync()
    } catch {
      error.value = 'Vollbild konnte nicht aktiviert werden.'
    }
  }
  async function exitFullscreen() {
    if (!browser || browser.fullscreenElement !== target.value || !target.value) return
    error.value = ''
    try {
      await browser.exitFullscreen()
      sync()
    } catch {
      error.value = 'Vollbild konnte nicht beendet werden. Bitte verwende die Browser-Steuerung.'
    }
  }
  function toggleFullscreen() {
    return isFullscreen.value ? exitFullscreen() : enterFullscreen()
  }
  onMounted(() => {
    browser = document
    browser.addEventListener('fullscreenchange', sync)
    sync()
  })
  watch(target, sync, { flush: 'post' })
  onBeforeUnmount(() => {
    browser?.removeEventListener('fullscreenchange', sync)
    // Also handles route leave. A different feature's fullscreen is never closed.
    void exitFullscreen()
  })
  return { isFullscreen, isSupported, error, enterFullscreen, exitFullscreen, toggleFullscreen }
}
