import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import CopyValueButton from '../../app/components/CopyValueButton.vue'

const views: ReturnType<typeof mount>[] = []
afterEach(() => {
  views.splice(0).forEach((view) => view.unmount())
  vi.unstubAllGlobals()
  vi.useRealTimers()
})
function render(props: {
  value: string | null
  label: string
  formatValue?: (value: string) => Promise<string>
}) {
  const view = mount(CopyValueButton, { props })
  views.push(view)
  return view
}

it('copies the exact value and announces success then clears the feedback', async () => {
  vi.useFakeTimers()
  const writeText = vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('navigator', { clipboard: { writeText } })
  const view = render({ value: '019e-uuid', label: 'UUID' })
  expect(view.get('button').attributes('aria-label')).toBe('UUID kopieren')
  await view.get('button').trigger('click')
  await flushPromises()
  expect(writeText).toHaveBeenCalledExactlyOnceWith('019e-uuid')
  expect(view.get('[role=status]').text()).toBe('Kopiert.')
  await vi.advanceTimersByTimeAsync(2500)
  expect(view.get('[role=status]').text()).toBe('')
})

it('reports unavailable clipboard access without leaking the underlying error', async () => {
  vi.stubGlobal('navigator', {
    clipboard: { writeText: vi.fn().mockRejectedValue(new Error('internal detail')) },
  })
  const view = render({ value: 'uuid', label: 'UUID' })
  await view.get('button').trigger('click')
  await flushPromises()
  expect(view.get('[role=status]').text()).toContain('Kopieren nicht verfügbar')
  expect(view.text()).not.toContain('internal detail')
})

it('disables null values and respects an explicit disabled state', async () => {
  const writeText = vi.fn()
  vi.stubGlobal('navigator', { clipboard: { writeText } })
  const view = render({ value: null, label: 'SQL' })
  expect(view.get('button').attributes('disabled')).toBeDefined()
  await view.get('button').trigger('click')
  await view.setProps({ value: 'SELECT 1', disabled: true })
  await view.get('button').trigger('click')
  expect(writeText).not.toHaveBeenCalled()
})

it('formats lazily and reuses only the current formatted value', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('navigator', { clipboard: { writeText } })
  const formatValue = vi.fn(async (value: string) => `formatted ${value}`)
  const view = render({ value: 'SELECT 1', label: 'SQL', formatValue })
  expect(formatValue).not.toHaveBeenCalled()
  for (let index = 0; index < 2; index++) {
    await view.get('button').trigger('click')
    await flushPromises()
  }
  expect(formatValue).toHaveBeenCalledTimes(1)
  expect(writeText).toHaveBeenLastCalledWith('formatted SELECT 1')
  await view.setProps({ value: 'SELECT 2' })
  expect(view.get('[role=status]').text()).toBe('')
  await view.get('button').trigger('click')
  await flushPromises()
  expect(writeText).toHaveBeenLastCalledWith('formatted SELECT 2')
})

it.each(['change', 'unmount'] as const)(
  'does not copy stale formatted content after %s',
  async (action) => {
    let resolve!: (value: string) => void
    const writeText = vi.fn()
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const view = render({
      value: 'old',
      label: 'SQL',
      formatValue: () =>
        new Promise<string>((done) => {
          resolve = done
        }),
    })
    await view.get('button').trigger('click')
    if (action === 'change') await view.setProps({ value: 'new' })
    else view.unmount()
    resolve('formatted old')
    await flushPromises()
    expect(writeText).not.toHaveBeenCalled()
  },
)
