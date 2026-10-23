#!/usr/bin/env node
/**
 * M2-CORE-INT-001 Phase B real-browser acceptance.
 *
 * Runs against the real production frontend bundle behind nginx and the real
 * API/proxy. It covers profile/snapshot behavior, flashcard Again/relearning,
 * session refresh recovery, 30-second heartbeats and tab pause, choice and
 * spelling grading, mistakes/restore, and the small-book option_count path.
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const STATE = JSON.parse(readFileSync(process.env.PHASE_B_STATE, 'utf8'))
const EVIDENCE_ROOT = process.env.EVIDENCE_DIR
const RUN_ID = process.env.LIVE_RUN_ID
const BASE_URL = process.env.LIVE_WEB_BASE_URL || STATE.web_base_url || 'http://127.0.0.1:8091'
const EDGE = process.env.LIVE_BROWSER_EXECUTABLE || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const PLAYWRIGHT_MODULE = process.env.LIVE_PLAYWRIGHT_MODULE || 'E:\\agent workspace\\英语学习工具\\ai-workspace\\10-collaboration\\sessions\\A20-VIEW\\temp\\a20-browser-check\\node_modules\\playwright-core\\index.mjs'
const RUN_DIR = join(EVIDENCE_ROOT, 'results', RUN_ID)
const SHOT_DIR = join(RUN_DIR, 'screenshots')
mkdirSync(SHOT_DIR, { recursive: true })
const { chromium } = await import(pathToFileURL(PLAYWRIGHT_MODULE).href)

const checks = []
const apiCalls = []
const consoleErrors = []
const httpErrors = []
const screenshots = {}
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

function record(name, ok, details = {}) {
  const status = ok ? 'PASS' : 'FAIL'
  checks.push({ name, status, details })
  console.log(`[${status}] ${name} ${JSON.stringify(details).slice(0, 500)}`)
  if (!ok) throw new Error(`CHECK FAILED: ${name}`)
}

async function waitForAnyText(page, text, timeout = 20000) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const body = await page.locator('body').innerText().catch(() => '')
    if (body.includes(text)) return body
    await sleep(120)
  }
  throw new Error(`text not visible: ${text}`)
}

async function waitForApi(method, pathPart, afterIndex = 0, timeout = 20000) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const found = apiCalls.find((call, index) => index >= afterIndex && call.method === method && call.path.includes(pathPart))
    if (found) return found
    await sleep(100)
  }
  throw new Error(`API call not observed: ${method} ${pathPart}`)
}

async function shot(page, name) {
  const path = join(SHOT_DIR, `${name}.png`)
  await page.screenshot({ path, fullPage: true })
  screenshots[name] = path
}

async function signIn(page, username, password) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' })
  await page.fill('#username', username)
  await page.fill('#password', password)
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 20000 }),
    page.click('button[type=submit]'),
  ])
  if (page.url().includes('/change-password')) {
    await page.fill('#old-password', password)
    await page.fill('#new-password', `${password}.Rotated1`)
    await page.fill('#confirm-password', `${password}.Rotated1`)
    await page.click('button[type=submit]')
    await page.waitForURL((url) => !url.pathname.startsWith('/change-password'), { timeout: 20000 })
  }
  await page.waitForLoadState('networkidle')
}

async function clickButton(page, label) {
  const button = page.getByRole('button', { name: label, exact: true })
  await button.waitFor({ state: 'visible', timeout: 20000 })
  await button.click()
}

function safeJsonBody(body) {
  if (!body || typeof body !== 'object') return body
  const out = { keys: Object.keys(body).sort() }
  for (const key of ['status', 'wordbook_id', 'session_id', 'item_id', 'event_id', 'option_count', 'credited_seconds', 'active_seconds_today']) {
    if (key in body) out[key] = body[key]
  }
  if (Array.isArray(body.items)) out.item_count = body.items.length
  if (body.card) out.card = { module: body.card.module, option_count: body.card.option_count, cloze: body.card.cloze }
  if (body.next_item) out.next_item = { reason: body.next_item.reason, position: body.next_item.position, completed: body.next_item.completed }
  return out
}

async function main() {
  const browser = await chromium.launch({ executablePath: EDGE, headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 960 }, locale: 'zh-CN' })
  const page = await context.newPage()
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push({ text: message.text().slice(0, 300), url: message.location()?.url || '' })
  })
  page.on('pageerror', (error) => consoleErrors.push({ text: String(error).slice(0, 300), url: 'pageerror' }))
  page.on('response', async (response) => {
    const url = response.url()
    if (!url.includes('/api/v1/')) return
    const call = {
      method: response.request().method(),
      path: new URL(url).pathname,
      status: response.status(),
      request_id: response.headers()['x-request-id'] || null,
    }
    if (response.status() >= 400) httpErrors.push({ status: response.status(), method: call.method, path: call.path })
    if (['/learning/', '/memory/', '/users/me/profile'].some((part) => url.includes(part)) && !url.includes('/auth/')) {
      try { call.body = safeJsonBody(await response.json()) } catch { /* non-JSON */ }
    }
    apiCalls.push(call)
  })

  try {
    await signIn(page, STATE.member_ui.username, STATE.member_ui.password)
    record('browser.member.login', !page.url().includes('/login'), { url: page.url() })

    await page.goto(`${BASE_URL}/settings`, { waitUntil: 'networkidle' })
    await waitForAnyText(page, '目标与记忆偏好')
    const beforeTarget = await page.locator('#daily-new-words').inputValue()
    record('browser.profile.loads-real-profile', beforeTarget === '8', { target: beforeTarget })
    await page.fill('#daily-new-words', '9')
    await page.click('button[type=submit]')
    await waitForAnyText(page, '档案已保存')
    await shot(page, '01-settings-saved')
    record('browser.profile.saves-next-day-target', true, { value: '9' })

    await page.goto(`${BASE_URL}/overview`, { waitUntil: 'networkidle' })
    await waitForAnyText(page, STATE.primary.name)
    const overviewText = await page.locator('body').innerText()
    record('browser.today.snapshot-stays-at-eight', overviewText.includes('/ 8') && overviewText.includes(STATE.primary.name), { sample: overviewText.slice(0, 280) })
    await shot(page, '02-overview-snapshot')

    await page.goto(`${BASE_URL}/memory`, { waitUntil: 'networkidle' })
    const flashBefore = apiCalls.length
    await page.getByRole('button', { name: /翻卡/ }).click()
    await page.locator('.study-card').waitFor({ state: 'visible', timeout: 20000 })
    const flashStart = await waitForApi('POST', '/memory/sessions', flashBefore)
    const flashSessionId = flashStart.body?.session_id
    record('browser.flashcard.real-session', Boolean(flashSessionId), { sessionId: flashSessionId })
    const firstFront = await page.locator('#flashcard-front').innerText()
    await page.locator('button.study-card__flip').click()
    await page.getByRole('button', { name: '无印象' }).click()
    await page.locator('.study-feedback').waitFor({ state: 'visible', timeout: 20000 })
    record('browser.flashcard.again-feedback', (await page.locator('.study-feedback').innerText()).includes('无印象'))
    await shot(page, '03-flashcard-again')

    let returned = false
    for (let attempt = 0; attempt < 12; attempt += 1) {
      await page.locator('.study-card').waitFor({ state: 'visible', timeout: 20000 })
      const front = await page.locator('#flashcard-front').innerText()
      if (front === firstFront) { returned = true; break }
      await page.locator('button.study-card__flip').click()
      await page.getByRole('button', { name: '有印象' }).click()
      await sleep(450)
    }
    record('browser.flashcard.again-requeued-after-gap', returned, { firstFront })
    await page.locator('button.study-card__flip').click()
    await page.getByRole('button', { name: '已记住' }).click()
    await waitForAnyText(page, '已记住')
    await shot(page, '04-flashcard-mastered')
    record('browser.flashcard.mastered-through-ui', true)

    const heartbeatBefore = apiCalls.length
    await page.mouse.move(500, 500)
    await page.keyboard.press('Shift')
    await sleep(31000)
    const heartbeat = await waitForApi('POST', '/learning/heartbeat', heartbeatBefore, 5000)
    record('browser.heartbeat.30-second-window', heartbeat.status === 200, { requestId: heartbeat.request_id })
    const hiddenBefore = apiCalls.filter((call) => call.path.includes('/learning/heartbeat')).length
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await sleep(300)
    const hiddenText = await page.locator('.memory-hero__state').innerText()
    await sleep(31000)
    const hiddenAfter = apiCalls.filter((call) => call.path.includes('/learning/heartbeat')).length
    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
      document.dispatchEvent(new Event('visibilitychange'))
    })
    // Returning from a hidden tab does not remove the 60s idle pause. The
    // frozen UI deliberately resumes only through a real card interaction, so
    // use one card action to verify that recovery path.
    await page.locator('button.study-card__flip').click()
    await page.getByRole('button', { name: '有印象' }).click()
    await sleep(450)
    const visibleText = await page.locator('.memory-hero__state').innerText()
    await shot(page, '05-heartbeat-paused')
    record('browser.heartbeat.pause-stops-requests', hiddenText.includes('已暂停') && hiddenAfter === hiddenBefore && visibleText.includes('计时中'), { hiddenText, hiddenAfter, hiddenBefore, visibleText })

    const resumeBefore = apiCalls.length
    await page.reload({ waitUntil: 'networkidle' })
    await page.getByRole('button', { name: /翻卡/ }).click()
    await page.locator('.study-card').waitFor({ state: 'visible', timeout: 20000 })
    const resumed = await waitForApi('POST', '/memory/sessions', resumeBefore)
    record('browser.session.refresh-recovery', resumed.body?.session_id === flashSessionId, { before: flashSessionId, after: resumed.body?.session_id })

    await page.goto(`${BASE_URL}/memory`, { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: /选择/ }).click()
    await page.locator('.study-card').waitFor({ state: 'visible', timeout: 20000 })
    const choicePrompt = (await page.locator('#choice-prompt').innerText()).trim()
    const choiceWord = STATE.word_map[choicePrompt]
    const optionLabels = await page.locator('.choice-option__label').allInnerTexts()
    const correctIndex = optionLabels.indexOf(choiceWord)
    record('browser.choice.server-options-no-leak', optionLabels.length === 4 && correctIndex >= 0, { prompt: choicePrompt, options: optionLabels })
    await page.locator('input[type=radio]').nth(correctIndex).check()
    await page.getByRole('button', { name: '提交答案' }).click()
    await page.locator('.study-feedback').waitFor({ state: 'visible', timeout: 20000 })
    const choiceFeedback = await page.locator('.study-feedback').innerText()
    record('browser.choice.server-grades-correct', choiceFeedback.includes('回答正确'), { feedback: choiceFeedback })
    await shot(page, '06-choice-correct')

    await page.goto(`${BASE_URL}/memory`, { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: /拼写/ }).click()
    await page.locator('.study-card').waitFor({ state: 'visible', timeout: 20000 })
    const spellingDefinition = (await page.locator('#spelling-definition').innerText()).trim()
    const spellingWord = STATE.word_map[spellingDefinition]
    const prefilled = page.locator('.spelling-cell--prefilled')
    const prefilledText = (await prefilled.count()) === 1 ? (await prefilled.first().innerText()).trim() : ''
    const blankInputCount = await page.locator('input.spelling-cell').count()
    record(
      'browser.spelling.first-letter-mask',
      Boolean(spellingWord) && prefilledText === spellingWord[0] && blankInputCount === spellingWord.length - 1,
      { definition: spellingDefinition, prefilled: prefilledText, blankInputCount, wordLength: spellingWord?.length },
    )
    const inputs = page.locator('input.spelling-cell')
    const inputCount = await inputs.count()
    for (let index = 0; index < inputCount; index += 1) {
      const input = inputs.nth(index)
      const label = await input.getAttribute('aria-label')
      const position = Number((label?.match(/\d+/) || [0])[0])
      if (position > 0) await input.fill(spellingWord[position - 1])
    }
    await page.getByRole('button', { name: '提交拼写' }).click()
    await page.locator('.study-feedback').waitFor({ state: 'visible', timeout: 20000 })
    const spellingFeedback = await page.locator('.study-feedback').innerText()
    record('browser.spelling.server-grades-correct', spellingFeedback.includes('回答正确'), { feedback: spellingFeedback })
    await shot(page, '07-spelling-first-letter')

    await page.goto(`${BASE_URL}/memory/mistakes`, { waitUntil: 'networkidle' })
    await waitForAnyText(page, '需要再练的词')
    const rows = page.locator('.mistake-table tbody tr')
    await rows.first().waitFor({ state: 'visible', timeout: 20000 })
    const firstRow = rows.filter({ hasText: firstFront }).first()
    record('browser.mistakes.again-word-visible', (await firstRow.count()) === 1, { word: firstFront })
    const priorityButton = firstRow.locator('.link-button')
    const wasPriority = (await priorityButton.getAttribute('aria-pressed')) === 'true'
    await priorityButton.click()
    await waitForAnyText(page, wasPriority ? '标为重点' : '已标记重点')
    record('browser.mistakes.priority-persists', true, { wasPriority })
    const restoreButton = firstRow.getByRole('button', { name: '恢复复习' })
    record('browser.mistakes.mastered-restore-button-visible', (await restoreButton.count()) === 1, { word: firstFront })
    await restoreButton.click()
    await waitForAnyText(page, '已恢复复习')
    record('browser.mistakes.restore-persists', true)
    await shot(page, '08-mistakes-restore')

    await context.clearCookies()
    await signIn(page, STATE.member_small.username, STATE.member_small.password)
    await page.goto(`${BASE_URL}/memory`, { waitUntil: 'networkidle' })
    await page.getByRole('button', { name: /选择/ }).click()
    await page.locator('.study-card').waitFor({ state: 'visible', timeout: 20000 })
    const smallOptions = await page.locator('.choice-option__label').allInnerTexts()
    record('browser.choice.option-count-less-than-four-renders', smallOptions.length === 2, { options: smallOptions })
    await page.locator('input[type=radio]').first().check()
    const submitSmall = page.getByRole('button', { name: '提交答案' })
    record('browser.choice.option-count-less-than-four-submit-enabled', await submitSmall.isEnabled(), { options: smallOptions.length })
    await submitSmall.click()
    await page.locator('.study-feedback').waitFor({ state: 'visible', timeout: 20000 })
    record('browser.choice.option-count-less-than-four-grades', (await page.locator('.study-feedback').innerText()).length > 0)
    await shot(page, '09-small-book-two-options')

    const authBoundary = (entry) => /status of 401/.test(entry.text) && /\/api\/v1\/auth\/(refresh|login)$/.test(entry.url)
    const unexpectedConsole = consoleErrors.filter((entry) => !authBoundary(entry))
    const unexpectedHttp = httpErrors.filter((entry) => !(entry.status === 401 && /\/api\/v1\/auth\/(refresh|login)$/.test(entry.path)))
    record('browser.console.no-unexpected-errors', unexpectedConsole.length === 0, { unexpected: unexpectedConsole.slice(0, 5), classifiedAuth401: consoleErrors.length - unexpectedConsole.length })
    record('browser.http.no-unexpected-error-status', unexpectedHttp.length === 0, { unexpected: unexpectedHttp.slice(0, 8) })

    const result = {
      task: 'M2-CORE-INT-001', phase: 'B', run_id: RUN_ID,
      browser: { engine: 'chromium', executable: EDGE, headless: true },
      finished_at: new Date().toISOString(), status: 'PASS', checks, screenshots,
      api_calls: apiCalls, console_errors: consoleErrors, http_errors: httpErrors,
    }
    writeFileSync(join(RUN_DIR, 'browser-acceptance.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8')
    console.log(`RESULT=PASS evidence=${join(RUN_DIR, 'browser-acceptance.json')}`)
  } catch (error) {
    process.exitCode = 1
    try { await shot(page, '99-failure-state') } catch { /* best effort */ }
    const result = {
      task: 'M2-CORE-INT-001', phase: 'B', run_id: RUN_ID,
      browser: { engine: 'chromium', executable: EDGE, headless: true },
      finished_at: new Date().toISOString(), status: 'FAIL', error: String(error?.stack || error),
      checks, screenshots, api_calls: apiCalls, console_errors: consoleErrors, http_errors: httpErrors,
    }
    writeFileSync(join(RUN_DIR, 'browser-acceptance.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8')
    console.error(String(error?.stack || error))
  } finally {
    await browser.close()
  }
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
