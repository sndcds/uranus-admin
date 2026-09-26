import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import LoginPanel from '../../app/components/LoginPanel.vue'
import { AdminApiError, failure } from '../../shared/errors'
const navigate = vi.fn()
const auth = { login: vi.fn(), isAdmin: true, canResearch: true, error: null }
beforeEach(() => {
  auth.login.mockReset().mockResolvedValue(undefined)
  vi.stubGlobal('useAuthStore', () => auth)
  vi.stubGlobal('useRoute', () => ({ query: { redirect: '/graph?depth=2' }, hash: '#details' }))
  vi.stubGlobal('navigateTo', navigate.mockReset())
})
afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})
it('renders labelled fields, submits with Enter semantics and restores the target', async () => {
  const wrapper = mount(LoginPanel)
  await flushPromises()
  expect(wrapper.get('input[autocomplete="username"]').attributes('id')).toBe('admin-login')
  expect(wrapper.get('input[autocomplete="current-password"]').attributes('type')).toBe('password')
  await wrapper.get('#admin-login').setValue('operator')
  await wrapper.get('#admin-password').setValue('synthetic-password')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(auth.login).toHaveBeenCalledWith('operator', 'synthetic-password')
  expect(navigate).toHaveBeenCalledWith('/graph?depth=2#details', { replace: true })
  expect(wrapper.get<HTMLInputElement>('#admin-password').element.value).toBe('')
})
it('disables submission while pending', async () => {
  let resolve!: () => void
  auth.login.mockReturnValue(
    new Promise<void>((r) => {
      resolve = r
    }),
  )
  const wrapper = mount(LoginPanel)
  await flushPromises()
  await wrapper.get('form').trigger('submit')
  expect(wrapper.get('button').attributes('disabled')).toBeDefined()
  await wrapper.get('form').trigger('submit')
  expect(auth.login).toHaveBeenCalledOnce()
  resolve()
  await flushPromises()
  expect(wrapper.get('button').attributes('disabled')).toBeUndefined()
})
it.each([
  [401, 'Anmeldung fehlgeschlagen.'],
  [429, 'Zu viele Anmeldeversuche.'],
])('announces login error %s and focuses password', async (status, message) => {
  auth.login.mockRejectedValue(new AdminApiError(failure(Number(status))))
  const wrapper = mount(LoginPanel, { attachTo: document.body })
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain(message)
  expect(document.activeElement).toBe(wrapper.get('#admin-password').element)
  expect(navigate).not.toHaveBeenCalled()
  wrapper.unmount()
})
