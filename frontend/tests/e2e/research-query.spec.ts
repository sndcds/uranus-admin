import { test, expect } from '../fixtures/authenticated'
import {
  executionResponse,
  countQuestion,
  sortedEventsQuestion,
  sortedEventsResponse,
} from '../fixtures/research-execution'
import { researchPage, researchCategories } from '../fixtures/research'
import { enforceProductionCsp } from '../fixtures/record-csp'
const root = '/api/admin/api/v1/research'
test.beforeEach(async ({ page, context }) => {
  const login = await context.request.post('/api/admin/auth/login', {
    headers: { Origin: 'http://127.0.0.1:3100', 'X-Admin-CSRF': '1' },
    data: { login: 'journalist', password: 'test-only-password' },
  })
  expect(login.status()).toBe(200)
  await enforceProductionCsp(page)
})
test('exact question answer, link/reload/history and independent search modes', async ({
  page,
  context,
}, info) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  let questions = 0
  let searches = 0
  await page.route(`**${root}/**`, async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/query')) {
      questions++
      expect(route.request().method()).toBe('POST')
      expect(route.request().postDataJSON()).toEqual({ query: countQuestion })
      expect(route.request().headers()['x-admin-csrf']).toBe('1')
      return route.fulfill({ json: executionResponse() })
    }
    if (path.endsWith('/options'))
      return route.fulfill({ json: { categories: researchCategories } })
    searches++
    return route.fulfill({ json: researchPage() })
  })
  await page.goto('/research')
  await page.getByRole('link', { name: 'Frage beantworten', exact: true }).click()
  await page.getByLabel('Deine Recherchefrage').fill(countQuestion)
  expect(questions).toBe(0)
  await page.getByRole('button', { name: 'Antwort anzeigen' }).click()
  await expect(page.getByTestId('research-count')).toHaveText('123 Veranstaltungen')
  await expect(page.getByText('Flensburg · 01.08.2026 – 31.08.2026', { exact: true })).toBeVisible()
  await expect(page.getByText('Exakte strukturierte Auswertung')).toBeVisible()
  expect(searches).toBe(0)
  expect(new URL(page.url()).searchParams.get('question')).toBe(countQuestion)
  await page.getByRole('button', { name: 'Frage-Link kopieren' }).click()
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(page.url())
  await page.reload()
  await expect(page.getByTestId('research-count')).toHaveText('123 Veranstaltungen')
  expect(questions).toBe(2)
  await page.screenshot({ path: info.outputPath('research-query-count.png'), fullPage: true })
  await page.getByText('So wurde die Frage verstanden').click()
  await expect(page.getByText('Europe/Berlin')).toBeVisible()
  await page.getByRole('button', { name: 'Treffer suchen', exact: true }).click()
  await expect(page.getByText('3 Ergebnisse insgesamt')).toBeVisible()
  expect(questions).toBe(2)
  await page.goBack()
  await expect(page.getByTestId('research-count')).toHaveText('123 Veranstaltungen')
  expect(questions).toBe(3)
  await page.goForward()
  await expect(page.getByText('3 Ergebnisse insgesamt')).toBeVisible()
})
test('semantic records show evidence and bounded selection, never an exact population', async ({
  page,
}, info) => {
  const response = executionResponse('records', true)
  await page.route(`**${root}/query`, (route) => route.fulfill({ json: response }))
  await page.goto(`/research/search?mode=answer&question=${encodeURIComponent(response.query)}`)
  await expect(page.getByText('Semantische Relevanzsuche · bis zu 20 Treffer')).toBeVisible()
  await expect(page.getByText(/Keine vollständige Zählung/)).toBeVisible()
  await expect(
    page.getByText(/Ergebnisse insgesamt|Es gibt \d|Exakte strukturierte Auswertung/),
  ).toHaveCount(0)
  await page.getByText('Beleg anzeigen', { exact: true }).click()
  await expect(page.getByText('Öffentlicher Jazzabend mit regionalen Künstlern.')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.evaluate(() => {
    ;(document.activeElement as HTMLElement | null)?.blur()
    window.scrollTo(0, 0)
  })
  await page.screenshot({ path: info.outputPath('research-query-semantic.png'), fullPage: true })
})
test('clarification offers editable candidates without a continuation request', async ({
  page,
}, info) => {
  const response = executionResponse('needs_clarification')
  let requests = 0
  await page.route(`**${root}/query`, (route) => {
    requests++
    return route.fulfill({ json: response })
  })
  await page.goto(`/research/search?mode=answer&question=${encodeURIComponent(response.query)}`)
  await expect(page.getByRole('heading', { name: 'Frage präzisieren' })).toBeVisible()
  await expect(page.getByText('Abruf fehlgeschlagen')).toHaveCount(0)
  await page.getByRole('button', { name: 'Neustadt in Holstein', exact: true }).click()
  await expect(page.getByLabel('Deine Recherchefrage')).toBeFocused()
  await expect(page.getByLabel('Deine Recherchefrage')).toHaveValue(
    response.query.replace('Neustadt', 'Neustadt in Holstein'),
  )
  expect(requests).toBe(1)
  expect(new URL(page.url()).searchParams.get('question')).toBe(response.query)
  await page.screenshot({
    path: info.outputPath('research-query-clarification.png'),
    fullPage: true,
  })
  await page.getByRole('button', { name: 'Antwort anzeigen' }).click()
  await expect.poll(() => requests).toBe(2)
})

test('first event renders the selected occurrence without semantic or count claims', async ({
  page,
}) => {
  const response = executionResponse('records')
  const query = 'wann war das erste event im system?'
  response.query = query
  Object.assign(response.plan.plan, {
    original_query: query,
    ordering: 'asc',
    limit: 1,
    temporal: 'none',
    explicit_from_date: null,
    explicit_to_date: null,
    area_query: null,
  })
  response.resolution = []
  response.execution.from_date = null
  response.execution.to_date = null
  if (response.result.kind !== 'records') throw new Error('fixture')
  response.result.total = null
  response.result.items[0]!.start_date = '2024-12-31'
  response.result.items[0]!.end_date = '2024-12-31'
  await page.route(`**${root}/query`, (route) => {
    expect(route.request().postDataJSON()).toEqual({ query })
    return route.fulfill({ json: response })
  })
  await page.goto(`/research/search?mode=answer&question=${encodeURIComponent(query)}`)
  await expect(page.getByText('Sortierung: Datum aufsteigend')).toBeVisible()
  await expect(page.getByText(/31\.12\.2024/).first()).toBeVisible()
  await expect(page.getByText(/Semantische Relevanzsuche|Ergebnisse insgesamt/)).toHaveCount(0)
})

test('explicit date sort and independent limit render two Flensburg records', async ({ page }) => {
  const response = sortedEventsResponse()
  await page.route(`**${root}/query`, (route) => {
    expect(route.request().postDataJSON()).toEqual({ query: sortedEventsQuestion })
    return route.fulfill({ json: response })
  })
  await page.goto(
    `/research/search?mode=answer&question=${encodeURIComponent(sortedEventsQuestion)}`,
  )
  const answer = page.getByRole('region', { name: 'Antwort', exact: true })
  await expect(answer.getByText('Sortierung: Datum aufsteigend')).toBeVisible()
  await expect(answer.getByText('Maximal 2 Ergebnisse')).toBeVisible()
  await expect(answer.getByText('Flensburg · Kein Datumsfilter', { exact: true })).toBeVisible()
  const cards = answer.locator('article')
  await expect(cards).toHaveCount(2)
  await expect(cards.nth(0)).toContainText('16.06.2025')
  await expect(cards.nth(1)).toContainText('27.09.2025')
  await expect(
    page.getByText(
      /research_plan_unsupported|Abruf fehlgeschlagen|Semantische Relevanzsuche|Ergebnisse insgesamt/,
    ),
  ).toHaveCount(0)
})
