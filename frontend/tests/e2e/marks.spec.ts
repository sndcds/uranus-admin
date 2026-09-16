import { test, expect } from '@playwright/test'
import type { MarkDetail, MarkCreate, MarkUpdate } from '../../shared/contracts'

const entityKey = '10000000-0000-4000-8000-000000000020'
const stamp = '2026-09-14T12:00:00Z'

test('marks retain notes, completion authors and reopening history across navigation', async ({
  page,
}, info) => {
  const records: MarkDetail[] = []
  await page.route('**/api/admin/api/v1/dashboard/activity**', (route) =>
    route.fulfill({
      json: {
        items: [
          {
            entity_type: 'venue',
            entity_key: entityKey,
            entity_name: 'Hafenbühne',
            organization_id: null,
            organization_name: null,
            created_at: stamp,
            status: null,
            action: null,
          },
        ],
        pagination: { page: 1, page_size: 50, total: 1, pages: 1 },
        observed_at: stamp,
        from_at: stamp,
        to_at: stamp,
        timestamp_state: 'known',
        unknown_timestamp_count: 0,
      },
    }),
  )
  await page.route('**/api/admin/api/v1/record-marks**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const id = url.pathname.split('/').at(-1)
    if (request.method() === 'POST') {
      const body = request.postDataJSON() as MarkCreate
      const record: MarkDetail = {
        id: `20000000-0000-4000-8000-${String(records.length + 1).padStart(12, '0')}`,
        entity_type: body.entity_type,
        entity_key: body.entity_key,
        entity_name: 'Hafenbühne',
        reasons: body.reasons,
        reason_detail: body.reason_detail ?? null,
        urgency: body.urgency,
        status: 'open',
        version: 1,
        created_at: stamp,
        created_by: 'Anna',
        updated_at: stamp,
        completed_at: null,
        completed_by: null,
        events: [],
      }
      record.events.push({
        id: record.id,
        version: 1,
        kind: 'created',
        author: 'Anna',
        created_at: stamp,
        note: body.note ?? null,
        status: record.status,
        reasons: record.reasons,
        reason_detail: record.reason_detail,
        urgency: record.urgency,
      })
      records.push(record)
      return route.fulfill({ status: 201, json: record })
    }
    const record = records.find((record) => record.id === id)
    if (record) {
      if (request.method() === 'PATCH') {
        const body = request.postDataJSON() as MarkUpdate
        expect(body).not.toHaveProperty('completed_by')
        expect(body).not.toHaveProperty('completed_at')
        expect(body.version).toBe(record.version)
        const previousStatus = record.status
        const time = `2026-09-14T12:${String(record.version).padStart(2, '0')}:00Z`
        Object.assign(record, {
          reasons: body.reasons,
          reason_detail: body.reason_detail ?? null,
          urgency: body.urgency,
          status: body.status,
          version: record.version + 1,
          updated_at: time,
        })
        if (previousStatus !== 'done' && body.status === 'done') {
          record.completed_at = time
          record.completed_by = 'Boris'
        } else if (body.status !== 'done') {
          record.completed_at = null
          record.completed_by = null
        }
        record.events.push({
          id: `30000000-0000-4000-8000-${String(record.version).padStart(12, '0')}`,
          version: record.version,
          kind:
            previousStatus === 'done' && body.status !== 'done'
              ? 'reopened'
              : previousStatus !== 'done' && body.status === 'done'
                ? 'completed'
                : 'updated',
          author: 'Boris',
          created_at: time,
          note: body.note ?? null,
          status: body.status,
          reasons: body.reasons,
          reason_detail: body.reason_detail ?? null,
          urgency: body.urgency,
        })
      }
      return route.fulfill({ json: record })
    }
    const status = url.searchParams.get('status') ?? 'active'
    const items = records.filter(
      (record) =>
        (status === 'all' ||
          (status === 'active' ? record.status !== 'done' : record.status === status)) &&
        (!url.searchParams.get('urgency') || record.urgency === url.searchParams.get('urgency')),
    )
    return route.fulfill({
      json: {
        items,
        pagination: { page: 1, page_size: 50, total: items.length, pages: items.length ? 1 : 0 },
      },
    })
  })
  await page.goto('/activity')
  await page.getByRole('link', { name: 'Markierungen & Notizen' }).click()
  await page.getByRole('button', { name: 'Neue Markierung' }).click()
  await page.getByLabel('Falsche Angaben', { exact: true }).check()
  await page.getByLabel('Geringe Qualität', { exact: true }).check()
  await page.getByRole('combobox', { name: 'Dringlichkeit', exact: true }).selectOption('urgent')
  await page.getByLabel('Notiz (optional)', { exact: true }).fill('Datum beim Veranstalter prüfen')
  await page.getByRole('button', { name: 'Markierung speichern', exact: true }).click()
  await expect(page).toHaveURL(/\/marks\/20000000-/)
  const detailURL = page.url()
  await expect(page.getByRole('region', { name: 'Notizen und Verlauf' })).toContainText('Anna')
  await page.getByLabel('Neue Notiz / Abschlussnotiz (optional)').fill('Veranstalter kontaktiert')
  await page
    .getByRole('combobox', { name: 'Bearbeitungsstatus', exact: true })
    .selectOption('in_progress')
  await page.getByRole('button', { name: 'Änderungen speichern' }).click()
  await expect(page.getByText('Markierung gespeichert.', { exact: true })).toBeVisible()
  await page.getByLabel('Neue Notiz / Abschlussnotiz (optional)').fill('Datum korrigiert')
  await page.getByRole('button', { name: 'Als erledigt markieren', exact: true }).click()
  await expect(page.getByText(/Erledigt am .* von Boris/)).toBeVisible()
  await page.reload()
  const history = page.getByRole('region', { name: 'Notizen und Verlauf' })
  await expect(history).toContainText('Datum beim Veranstalter prüfen')
  await expect(history).toContainText('Veranstalter kontaktiert')
  await expect(history).toContainText('Datum korrigiert')
  await page.getByRole('button', { name: 'Wieder öffnen', exact: true }).click()
  await expect(history.getByText('Wieder geöffnet', { exact: true })).toBeVisible()
  await expect(page.getByText(/Erledigt am .* von Boris/)).toHaveCount(0)
  await expect(history.getByText('Als erledigt markiert', { exact: true })).toBeVisible()
  // A second concern on the same record remains independent.
  await page.getByRole('link', { name: 'Markierungen & Notizen' }).click()
  await page.getByRole('button', { name: 'Neue Markierung' }).click()
  await page.getByLabel('Sonstiges', { exact: true }).check()
  await page.getByLabel('Erläuterung zum Grund (erforderlich)').fill('Bild prüfen')
  await page.getByRole('button', { name: 'Markierung speichern', exact: true }).click()
  await expect(page).not.toHaveURL(detailURL)
  await page.goto(detailURL)
  await page.getByRole('button', { name: 'Als erledigt markieren', exact: true }).click()
  await expect(page.getByText(/Erledigt am .* von Boris/)).toBeVisible()
  await page.goto('/marks')
  await expect(page.getByText('1 Markierungen insgesamt', { exact: true })).toBeVisible()
  await expect(
    page.getByRole('main').getByRole('listitem').getByText('Offen', { exact: true }),
  ).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('marks.png'), fullPage: true })
  await page.getByRole('combobox', { name: 'Status', exact: true }).selectOption('done')
  await page
    .getByRole('combobox', { name: 'Dringlichkeit filtern', exact: true })
    .selectOption('urgent')
  await page.getByRole('button', { name: 'Anwenden' }).click()
  await expect(page).toHaveURL(/status=done/)
  await expect(page.getByText(/Erledigt am .* von Boris/)).toBeVisible()
  expect(records).toHaveLength(2)
  expect(records[1]?.status).toBe('open')
})

test('real proxy protects mark authors and rejects unauthenticated mutations', async ({
  request,
}) => {
  const create = {
    entity_type: 'venue',
    entity_key: entityKey,
    reasons: ['incorrect'],
    urgency: 'normal',
  }
  expect((await request.post('/api/admin/api/v1/record-marks', { data: create })).status()).toBe(
    401,
  )
  expect(
    (
      await request.patch(`/api/admin/api/v1/record-marks/${entityKey}`, {
        data: { version: 1, status: 'done', reasons: ['incorrect'], urgency: 'normal' },
      })
    ).status(),
  ).toBe(401)
  expect(
    (
      await request.post('/api/admin/api/v1/record-marks', {
        headers: { Authorization: 'Bearer fixture-token' },
        data: { ...create, created_by: 'forged' },
      })
    ).status(),
  ).toBe(422)
})
