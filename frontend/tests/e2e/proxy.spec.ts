import { test, expect } from '../fixtures/authenticated'
import { geocodeDetail } from '../fixtures/geocoding'
import { failure } from '../../shared/errors'

const assignmentPath = `/api/admin/api/v1/assignments?workflow_type=geocode_request&workflow_key=${geocodeDetail.id}`

test('real proxy preserves JSON null, object responses and sanitized upstream errors', async ({
  page,
}) => {
  await page.goto('/login')
  // Browser fetch sends the HttpOnly cookie in both development and production.
  // No API interception: these requests exercise Nitro and the controlled upstream.
  const responses = await page.evaluate(
    async (paths) => {
      return Promise.all(
        paths.map(async (path) => {
          const response = await fetch(path)
          return {
            status: response.status,
            contentType: response.headers.get('content-type'),
            cacheControl: response.headers.get('cache-control'),
            body: await response.text(),
          }
        }),
      )
    },
    [assignmentPath, '/api/admin/api/v1/admins', `/api/admin/api/v1/geo/areas/${geocodeDetail.id}`],
  )
  expect(responses[0]).toEqual({
    status: 200,
    contentType: 'application/json; charset=utf-8',
    cacheControl: 'private, no-store',
    body: 'null',
  })
  expect(responses[1]!.status).toBe(200)
  expect(responses[1]!.contentType).toContain('application/json')
  expect(JSON.parse(responses[1]!.body)).toEqual({
    items: [{ id: '00000000-0000-4000-8000-000000000800', login: 'operator' }],
    admin_timezone: 'Europe/Berlin',
  })
  expect(responses[2]!.status).toBe(404)
  expect(responses[2]!.contentType).toContain('application/json')
  expect(JSON.parse(responses[2]!.body)).toEqual({
    error: {
      code: 'geo_scope_not_found',
      message: failure(404, 'geo_scope_not_found').message,
    },
  })
})

test('unassigned workflow shows operator in AssignmentEditor through the real proxy', async ({
  page,
}) => {
  // Only the domain detail is mocked; admins and assignments go through Nitro.
  await page.route('**/api/admin/api/v1/geocode/requests/*', (route) =>
    route.fulfill({ json: geocodeDetail }),
  )
  const assignmentResponse = page.waitForResponse((response) =>
    response.url().endsWith(assignmentPath),
  )
  await page.goto(`/geocoding/${geocodeDetail.id}`)
  const response = await assignmentResponse
  expect(response.status()).toBe(200)
  expect(await response.text()).toBe('null')
  const editor = page.getByRole('region', { name: 'Zuständigkeit', exact: true })
  const assignee = editor.getByRole('combobox', { name: 'Zuständig', exact: true })
  await expect(assignee).toBeVisible()
  await expect(assignee).toHaveValue('00000000-0000-4000-8000-000000000800')
  await expect(assignee.getByRole('option', { name: 'operator', exact: true })).toHaveCount(1)
  await expect(editor.getByRole('button', { name: 'Aufgabe zuweisen' })).toBeEnabled()
  await expect(editor.getByRole('alert')).toHaveCount(0)
  await expect(editor).not.toContainText('Zuständigkeit konnte nicht geladen werden.')
})
