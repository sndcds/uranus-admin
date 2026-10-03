import { readFileSync } from 'node:fs'
import { mount } from '@vue/test-utils'
import { expect, it } from 'vitest'
import { nextTick } from 'vue'
import ResearchComposer from '../../app/components/ResearchComposer.vue'

function composer(overrides = {}) {
  return mount(ResearchComposer, {
    props: {
      modelValue: 'Kultur in Flensburg',
      busy: false,
      disabled: false,
      invalid: false,
      expanded: false,
      activeSuggestion: -1,
      ...overrides,
    },
    global: { stubs: { AppIcon: true } },
  })
}
it.each([{}, { ctrlKey: true }, { metaKey: true }])('Enter submits once with %j', async (keys) => {
  const view = composer()
  const event = new KeyboardEvent('keydown', { key: 'Enter', ...keys, cancelable: true })
  view.get('textarea').element.dispatchEvent(event)
  expect(event.defaultPrevented).toBe(true)
  expect(view.emitted('submit')).toHaveLength(1)
  view.unmount()
})
it.each([{ shiftKey: true }, { isComposing: true }, { keyCode: 229 }])(
  'preserves newline/IME behavior with %j',
  (keys) => {
    const view = composer()
    const event = new KeyboardEvent('keydown', { key: 'Enter', ...keys, cancelable: true })
    view.get('textarea').element.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(false)
    expect(view.emitted('submit')).toBeUndefined()
    view.unmount()
  },
)
it('lets suggestion selection consume Enter without a second submission', () => {
  const view = composer({ onKeydown: (event: KeyboardEvent) => event.preventDefault() })
  view
    .get('textarea')
    .element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', cancelable: true }))
  expect(view.emitted('submit')).toBeUndefined()
  view.unmount()
})
it.each([{ busy: true }, { disabled: true }, { modelValue: '   ' }])(
  'blocks button, keyboard and form submission when unavailable: %j',
  async (state) => {
    const view = composer(state)
    expect(view.get('button').attributes('disabled')).toBeDefined()
    await view.get('textarea').trigger('keydown', { key: 'Enter' })
    await view.get('form').trigger('submit')
    expect(view.emitted('submit')).toBeUndefined()
    view.unmount()
  },
)
it('keeps only the labeled textarea, count and send control inside its form', () => {
  const view = composer()
  expect(view.findAll('textarea')).toHaveLength(1)
  expect(view.get('label').attributes('for')).toBe(view.get('textarea').attributes('id'))
  expect(view.findAll('button')).toHaveLength(1)
  expect(view.get('form button').attributes('aria-label')).toBe('Antwort anzeigen')
  expect(view.get('form .research-composer-count').text()).toBe('19/2.000')
  expect(view.find('input[type="file"]').exists()).toBe(false)
  expect(view.get('form').attributes('aria-busy')).toBe('false')
  view.unmount()
})
it('grows and shrinks on external edits without replacing the textarea', async () => {
  const view = composer()
  const input = view.get('textarea').element
  let height = 144
  Object.defineProperty(input, 'scrollHeight', { get: () => height })
  await view.setProps({ modelValue: 'Mehrere\nZeilen' })
  await nextTick()
  expect(input.style.height).toBe('144px')
  height = 32
  await view.setProps({ modelValue: 'Kurz' })
  await nextTick()
  expect(input.style.height).toBe('32px')
  expect(view.get('textarea').element).toBe(input)
  view.unmount()
})

it('has no attachment controls, drag/drop handlers or viewport-wide positioning', () => {
  const source = readFileSync('app/components/ResearchComposer.vue', 'utf8')
  expect(source).not.toMatch(
    /@(drop|drag[a-z]*)|on(Drop|Drag)|type=["']file|paperclip|upload|attachment/i,
  )
  expect(source).not.toMatch(/100vw|position:\s*fixed/)
  expect(source).toContain('max-height: min(12rem, 25dvh)')
})
