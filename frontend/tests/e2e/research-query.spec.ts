import { researchSuggestions, suggestionReceipt } from '../fixtures/research-suggestions'
import { test, expect } from '../fixtures/authenticated'
import {
  executionResponse,
  eventOccurrencesResponse,
  eventOccurrencesQuestion,
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
  await page.route(`**${root}/suggestions?**`, (route) =>
    route.fulfill({ json: { request_id: researchSuggestions.request_id, suggestions: [] } }),
  )
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
    if (path.endsWith('/suggestions'))
      return route.fulfill({
        json: { request_id: researchSuggestions.request_id, suggestions: [] },
      })
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
  await expect(page.getByLabel('Deine Recherchefrage')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Frage beantworten', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Frage beantworten', exact: true })).toHaveCount(0)
  await page.getByLabel('Deine Recherchefrage').fill(countQuestion)
  expect(questions).toBe(0)
  await page.getByRole('button', { name: 'Antwort anzeigen' }).click()
  await expect(page.getByTestId('research-count')).toHaveText('123 Veranstaltungen')
  await expect(page.getByText('Flensburg · 01.08.2026 – 31.08.2026', { exact: true })).toBeVisible()
  await expect(page.getByText('Exakte strukturierte Auswertung')).toBeVisible()
  expect(searches).toBe(0)
  expect(new URL(page.url()).pathname).toBe('/research')
  expect(new URL(page.url()).searchParams.get('question')).toBe(countQuestion)
  await page.getByRole('button', { name: 'Frage-Link kopieren' }).click()
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(page.url())
  await page.reload()
  await expect(page.getByTestId('research-count')).toHaveText('123 Veranstaltungen')
  expect(questions).toBe(2)
  await page.screenshot({ path: info.outputPath('research-query-count.png'), fullPage: true })
  await page.getByText('So wurde die Frage verstanden').click()
  await expect(page.getByText('Europe/Berlin')).toBeVisible()
  await page.getByRole('link', { name: 'Klassische Suche', exact: true }).click()
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
  expect(new URL(page.url()).pathname).toBe('/research')
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

test('learned autosuggest renders, selects and passes receipt without changing the question body', async ({
  page,
}) => {
  let impressions = 0
  let selections = 0
  await page.route(`**${root}/suggestions?**`, (route) =>
    route.fulfill({ json: researchSuggestions }),
  )
  await page.route(`**${root}/suggestions/impression`, (route) => {
    impressions++
    expect(route.request().postDataJSON()).toEqual({
      request_id: researchSuggestions.request_id,
      prefix: 'Wie viele',
      suggestions: [{ id: researchSuggestions.suggestions[0]!.id, position: 1 }],
    })
    return route.fulfill({ json: { ok: true, receipt: null } })
  })
  await page.route(`**${root}/suggestions/select`, (route) => {
    selections++
    expect(route.request().postDataJSON()).toEqual({
      request_id: researchSuggestions.request_id,
      suggestion_id: researchSuggestions.suggestions[0]!.id,
      position: 1,
    })
    return route.fulfill({ json: { ok: true, receipt: suggestionReceipt } })
  })
  await page.route(`**${root}/query`, (route) => {
    expect(route.request().postDataJSON()).toEqual({
      query: researchSuggestions.suggestions[0]!.query,
    })
    expect(route.request().headers()['x-research-selection']).toBe(suggestionReceipt)
    return route.fulfill({ json: executionResponse() })
  })
  await page.goto('/research')
  const question = page.getByRole('combobox', { name: 'Deine Recherchefrage' })
  await question.fill('Wie viele')
  await expect(page.getByRole('option')).toHaveCount(1)
  await question.press('ArrowDown')
  await question.press('Enter')
  await expect(page.getByTestId('research-count')).toBeVisible()
  expect(impressions).toBe(1)
  expect(selections).toBe(1)
  expect(new URL(page.url()).searchParams.has('receipt')).toBe(false)
})

test('homepage examples, keyboard, loading and responsive layout', async ({ page }, info) => {
  let requests = 0
  let release!: () => void
  const response = executionResponse('records')
  if (response.result.kind !== 'records') throw new Error('fixture')
  response.result.items = []
  response.result.total = 0
  await page.route(`**${root}/query`, async (route) => {
    requests++
    await new Promise<void>((resolve) => {
      release = resolve
    })
    await route.fulfill({ json: response })
  })
  await page.goto('/research')
  const input = page.getByLabel('Deine Recherchefrage')
  const examples = page.getByRole('group', { name: 'Beispiele für Fragen' })
  await expect(input).toBeEnabled()
  await expect(examples.getByRole('button')).toHaveCount(4)
  await page.screenshot({ path: info.outputPath('research-homepage.png'), fullPage: true })
  for (const width of [390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await expect(page.getByRole('button', { name: 'Antwort anzeigen' })).toBeInViewport()
  }
  await examples
    .getByRole('button', { name: 'Wo finden Jazz-Konzerte statt?', exact: true })
    .click()
  await expect(input).toBeFocused()
  await expect(input).toHaveValue('Wo finden Jazz-Konzerte statt?')
  expect(requests).toBe(0)
  await input.press('End')
  await input.press('Shift+Enter')
  await input.press('Enter')
  await expect(input).toHaveValue('Wo finden Jazz-Konzerte statt?\n\n')
  expect(requests).toBe(0)
  await input.press('Control+Enter')
  await expect(page.getByText('Frage wird ausgewertet …')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Antwort anzeigen' })).toBeDisabled()
  await input.press('Control+Enter')
  expect(requests).toBe(1)
  release()
  await expect(page.getByText('Keine passenden Datensätze gefunden.')).toBeVisible()
  await expect(page.getByText('Abruf fehlgeschlagen')).toHaveCount(0)
  await expect(input).toBeVisible()
  expect(new URL(page.url()).pathname).toBe('/research')
})

test('homepage API errors keep the editable question and allow retry', async ({ page }) => {
  await page.route(`**${root}/query`, (route) =>
    route.fulfill({
      status: 503,
      json: { error: { code: 'research_planner_unavailable', message: 'provider-secret' } },
    }),
  )
  await page.goto(`/research?question=${encodeURIComponent(countQuestion)}`)
  await expect(page.getByRole('button', { name: 'Erneut versuchen' })).toBeVisible()
  await expect(page.getByLabel('Deine Recherchefrage')).toHaveValue(countQuestion)
  await expect(page.getByText('provider-secret')).toHaveCount(0)
  await page.route(`**${root}/query`, (route) => route.fulfill({ json: executionResponse() }))
  await page.getByRole('button', { name: 'Erneut versuchen' }).click()
  await expect(page.getByTestId('research-count')).toHaveText('123 Veranstaltungen')
})

test('empty semantic selection explains that no sufficiently relevant events were found', async ({
  page,
}) => {
  const response = executionResponse('records', true)
  if (response.result.kind !== 'records') throw new Error('Expected records fixture')
  response.result.items = []
  await page.route(`**${root}/query`, (route) => route.fulfill({ json: response }))
  await page.goto(`/research/search?mode=answer&question=${encodeURIComponent(response.query)}`)
  await expect(
    page.getByText('Keine ausreichend passenden Veranstaltungen gefunden.'),
  ).toBeVisible()
  await expect(page.getByText('Abruf fehlgeschlagen')).toHaveCount(0)
  await expect(page.getByText('Warum passt das?')).toHaveCount(0)
  await expect(page.getByText(/Exakte strukturierte Auswertung|Ergebnisse insgesamt/)).toHaveCount(
    0,
  )
})

test('event with most dates displays the event rather than its type', async ({ page }) => {
  await page.route(`**${root}/query`, (route) => {
    expect(route.request().postDataJSON()).toEqual({ query: eventOccurrencesQuestion })
    return route.fulfill({ json: eventOccurrencesResponse() })
  })
  await page.goto('/research')
  await page.getByLabel('Deine Recherchefrage').fill(eventOccurrencesQuestion)
  await page.getByRole('button', { name: 'Antwort anzeigen' }).click()
  await expect(page.getByText('Termine nach Veranstaltung', { exact: false })).toBeVisible()
  const table = page.getByRole('table', { name: 'Auswertung' })
  await expect(table.getByRole('link', { name: 'Event 30', exact: true })).toHaveAttribute(
    'href',
    '/research/events/00000000-0000-0000-0000-00000000001e',
  )
  await expect(table.getByRole('cell', { name: '6', exact: true })).toBeVisible()
  await expect(page.getByText('Termine nach Veranstaltungstyp', { exact: false })).toHaveCount(0)
  await expect(table.getByText('Konzert')).toHaveCount(0)
})
