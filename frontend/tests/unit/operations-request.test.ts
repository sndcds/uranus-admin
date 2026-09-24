import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { expect, it } from 'vitest'
import { useOperationsRequest } from '../../app/composables/useOperationsRequest'
import { AdminApiError, failure } from '../../shared/errors'

function render() {
  let state!: ReturnType<typeof useOperationsRequest<string>>
  const view = mount(
    defineComponent({
      setup() {
        state = useOperationsRequest<string>()
        return () => null
      },
    }),
  )
  return { state, view }
}
it('retains same-selection data on refresh and transient failure, but clears identity/auth/invalid selections', async () => {
  const { state, view } = render()
  await state.load('one', async () => 'first')
  let resolve!: (value: string) => void
  const pending = state.load(
    'one',
    () =>
      new Promise((done) => {
        resolve = done
      }),
  )
  expect(state.data.value).toBe('first')
  expect(state.loading.value).toBe(true)
  resolve('refreshed')
  await pending
  await state.load('one', async () => {
    throw new AdminApiError(failure(503))
  })
  expect(state.data.value).toBe('refreshed')
  expect(state.error.value?.status).toBe(503)
  for (const status of [401, 403, 404, 422]) {
    await state.load('one', async () => 'first')
    await state.load('one', async () => {
      throw new AdminApiError(failure(status))
    })
    expect(state.data.value).toBeNull()
  }
  await state.load('one', async () => 'first')
  const changed = state.load(
    'two',
    () =>
      new Promise((done) => {
        resolve = done
      }),
  )
  expect(state.data.value).toBeNull()
  resolve('second')
  await changed
  view.unmount()
})
it('discards late success/error after selection changes and unmount', async () => {
  const { state, view } = render()
  let resolve!: (value: string) => void
  let reject!: (reason: unknown) => void
  const old = state.load(
    'one',
    () =>
      new Promise((done) => {
        resolve = done
      }),
  )
  const failed = state.load(
    'two',
    () =>
      new Promise((_done, fail) => {
        reject = fail
      }),
  )
  await state.load('three', async () => 'current')
  resolve('obsolete')
  reject(new AdminApiError(failure(403)))
  await Promise.all([old, failed])
  expect(state.data.value).toBe('current')
  expect(state.error.value).toBeNull()
  const last = state.load(
    'four',
    () =>
      new Promise((done) => {
        resolve = done
      }),
  )
  view.unmount()
  resolve('after unmount')
  await last
  await flushPromises()
  expect(state.data.value).toBeNull()
})
