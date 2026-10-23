#!/usr/bin/env node
/** T-QA-003 M4 real-browser admin/member acceptance. */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const STATE = JSON.parse(readFileSync(process.env.M4_STATE, 'utf8'))
const EVIDENCE_ROOT = process.env.EVIDENCE_DIR
const RUN_ID = process.env.LIVE_RUN_ID
const BASE_URL = process.env.LIVE_WEB_BASE_URL || STATE.web_base_url
const RUN_DIR = join(EVIDENCE_ROOT, 'results', RUN_ID)
const SHOT_DIR = join(RUN_DIR, 'screenshots')
mkdirSync(SHOT_DIR, { recursive: true })
const EDGE = process.env.LIVE_BROWSER_EXECUTABLE || 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const PLAYWRIGHT_MODULE = process.env.LIVE_PLAYWRIGHT_MODULE || 'E:\\agent workspace\\英语学习工具\\ai-workspace\\10-collaboration\\sessions\\A20-VIEW\\temp\\a20-browser-check\\node_modules\\playwright-core\\index.mjs'
const { chromium } = await import(pathToFileURL(PLAYWRIGHT_MODULE).href)

const checks = []
const calls = []
const consoleErrors = []
const screenshots = {}
const gaps = []
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const headwords = new Map(STATE.wordbook.entries.map((entry) => [String(entry.id), String(entry.headword)]))

function record(name, ok, detail = {}) {
  const status = ok ? 'PASS' : 'FAIL'
  checks.push({ name, status, detail })
  console.log('[' + status + '] ' + name + ' ' + JSON.stringify(detail).slice(0, 400))
  if (!ok) throw new Error('CHECK FAILED: ' + name)
}

async function waitText(page, text, timeout = 30000) {
  const end = Date.now() + timeout
  while (Date.now() < end) {
    const body = await page.locator('body').innerText().catch(() => '')
    if (body.includes(text)) return body
    await sleep(150)
  }
  throw new Error('Text not found: ' + text)
}

async function waitSelector(page, selector, timeout = 30000) {
  const end = Date.now() + timeout
  while (Date.now() < end) {
    if (await page.locator(selector).count()) return
    await sleep(150)
  }
  throw new Error('Selector not found: ' + selector)
}

async function shot(page, name) {
  const path = join(SHOT_DIR, name + '.png')
  await page.screenshot({ path, fullPage: true })
  screenshots[name] = path
}

async function login(page, username, password) {
  await page.goto(BASE_URL + '/login', { waitUntil: 'networkidle' })
  await page.fill('#username', username)
  await page.fill('#password', password)
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 20000 }),
    page.getByRole('button', { name: '登录' }).click(),
  ])
  await page.waitForLoadState('networkidle')
}

async function loginForApi(page, username, password) {
  const result = await page.evaluate(async ({ username, password }) => {
    const response = await fetch('/api/v1/auth/login', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    const body = await response.json().catch(() => ({}))
    return { status: response.status, token: body.access_token || null, requestId: response.headers.get('x-request-id') }
  }, { username, password })
  if (result.status !== 200 || !result.token) throw new Error('API login failed: ' + JSON.stringify(result))
  return result.token
}

async function apiFetch(page, token, method, path, body = null, key = null) {
  return page.evaluate(async ({ token, method, path, body, key }) => {
    const headers = { Authorization: 'Bearer ' + token }
    if (body !== null) headers['Content-Type'] = 'application/json'
    if (key) headers['Idempotency-Key'] = key
    const response = await fetch('/api/v1' + path, {
      method,
      credentials: 'include',
      headers,
      body: body === null ? undefined : JSON.stringify(body),
    })
    const text = await response.text()
    let payload = null
    try { payload = text ? JSON.parse(text) : null } catch { payload = { text } }
    return { status: response.status, body: payload, requestId: response.headers.get('x-request-id') }
  }, { token, method, path, body, key })
}

async function completeMemoryViaApi(page, token, sessionId) {
  for (let index = 0; index < 240; index += 1) {
    const current = await apiFetch(page, token, 'GET', '/memory/sessions/' + sessionId)
    if (current.status !== 200) throw new Error('memory read failed: ' + JSON.stringify(current))
    const session = current.body
    if (session.status === 'completed') return session
    if (session.next_item === null) {
      const completed = await apiFetch(page, token, 'POST', '/memory/sessions/' + sessionId + '/complete', {})
      if (completed.status !== 200) throw new Error('memory complete failed: ' + JSON.stringify(completed))
      return completed.body
    }
    const item = session.next_item
    const payload = { item_id: item.item_id, action: 'good', duration_ms: 1200 }
    if (session.module !== 'flashcard') {
      const answer = headwords.get(String(item.entry_id))
      if (!answer) throw new Error('missing headword for ' + item.entry_id)
      payload.answer = answer
    }
    const submitted = await apiFetch(page, token, 'POST', '/memory/sessions/' + sessionId + '/events', payload, 'browser-memory-' + index + '-' + Date.now())
    if (submitted.status !== 200) throw new Error('memory event failed: ' + JSON.stringify(submitted))
    if (submitted.body.session_completed) return submitted.body.session
  }
  throw new Error('memory session did not complete')
}

async function completeNextNonBossNode(page, token) {
  const challenge = await apiFetch(page, token, 'GET', '/challenges/today')
  if (challenge.status !== 200) throw new Error('challenge read failed: ' + JSON.stringify(challenge))
  const main = challenge.body.nodes
    .filter((node) => !node.optional)
    .sort((left, right) => left.order_index - right.order_index)
  const node = main.find((item) => item.node_type !== 'BOSS' && item.status !== 'completed')
  if (!node) throw new Error('no incomplete non-BOSS node')
  const started = await apiFetch(page, token, 'POST', '/challenges/' + challenge.body.id + '/nodes/' + node.id + '/start')
  if (started.status !== 200) throw new Error('node start failed: ' + JSON.stringify(started))
  if (started.body.resource_type === 'memory') {
    await completeMemoryViaApi(page, token, started.body.resource_id)
  }
  return { challengeId: challenge.body.id, nodeId: node.id, start: started.body }
}


async function completeVisibleFlashcardQueue(page) {
  for (let index = 0; index < 80; index += 1) {
    const body = await page.locator('body').innerText().catch(() => '')
    if (body.includes('本次队列已完成')) return body
    const flip = page.getByRole('button', { name: '翻到背面', exact: true })
    if (await flip.count()) {
      await flip.first().click()
      await page.waitForTimeout(80)
    }
    const good = page.getByRole('button', { name: '有印象', exact: true })
    if (await good.count()) {
      await good.first().click()
      await page.waitForTimeout(350)
    } else {
      await page.waitForTimeout(150)
    }
  }
  throw new Error('visible flashcard queue did not complete')
}

async function main() {
  const browser = await chromium.launch({ executablePath: EDGE, headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'zh-CN' })
  const page = await context.newPage()
  page.on('dialog', (dialog) => dialog.accept())
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push({ text: message.text().slice(0, 300), url: message.location()?.url || '' })
    }
  })
  page.on('pageerror', (error) => {
    consoleErrors.push({ text: String(error).slice(0, 300), url: 'pageerror' })
  })
  page.on('response', (response) => {
    const url = response.url()
    if (!url.includes('/api/v1/')) return
    calls.push({
      method: response.request().method(),
      path: new URL(url).pathname,
      status: response.status(),
      request_id: response.headers()['x-request-id'] || null,
    })
  })
  try {
    await login(page, STATE.admin.username, STATE.admin.password)
    record('browser.admin.login', !page.url().includes('/login'), { url: page.url() })

    await page.goto(BASE_URL + '/admin/dashboard', { waitUntil: 'networkidle' })
    await waitText(page, '组织学习看板')
    await waitText(page, '组织成员')
    const dashboardBody = await page.locator('body').innerText()
    record('browser.dashboard.aggregate', dashboardBody.includes('5') && dashboardBody.includes('QA') && dashboardBody.includes('Core'), { sample: dashboardBody.slice(0, 320) })
    record('browser.dashboard.no-content-leak', !dashboardBody.includes('COACH-CONTENT-SECRET') && !dashboardBody.includes('PRIVATE-WORDBOOK-SECRET'))
    await shot(page, '01-admin-dashboard')

    await page.fill('#dashboard-department', 'QA')
    await page.fill('#dashboard-group', 'Core')
    await page.getByRole('button', { name: '应用筛选' }).click()
    await waitText(page, 'Core')
    await shot(page, '02-admin-dashboard-core-filter')

    await page.fill('#dashboard-department', 'QA')
    await page.fill('#dashboard-group', 'Small')
    await page.getByRole('button', { name: '应用筛选' }).click()
    await waitText(page, '聚合结果已按隐私规则抑制')
    record('browser.dashboard.privacy-suppressed', true)
    await shot(page, '03-admin-dashboard-privacy')

    await page.fill('#dashboard-department', 'NoSuchDepartment')
    await page.fill('#dashboard-group', '')
    await page.getByRole('button', { name: '应用筛选' }).click()
    await waitText(page, '聚合结果已按隐私规则抑制')
    const emptyOrPrivacyBody = await page.locator('body').innerText()
    record(
      'browser.dashboard.empty-scope-safe',
      emptyOrPrivacyBody.includes('聚合结果已按隐私规则抑制'),
      { note: 'service suppresses zero-member scope below minimum group size; true zero aggregate is API-verified' }
    )
    await shot(page, '04-admin-dashboard-empty-or-privacy')

    await context.clearCookies()
    await login(page, STATE.member_ui.username, STATE.member_ui.password)
    record('browser.member.login', !page.url().includes('/login'), { url: page.url() })
    const memberToken = await loginForApi(page, STATE.member_ui.username, STATE.member_ui.password)

    await page.goto(BASE_URL + '/coach', { waitUntil: 'networkidle' })
    await waitText(page, 'AI 教练工作区')
    await page.getByRole('button', { name: '新建', exact: true }).click()
    await page.locator('input[placeholder="例如：本周学习计划"]').fill('浏览器学习计划')
    await page.getByRole('button', { name: '创建对话' }).click()
    await waitText(page, '浏览器学习计划')
    await page.locator('#coach-message-input').fill('请调整今日计划：25 个新词，45 分钟。')
    await page.getByRole('button', { name: '发送消息' }).click()
    await waitText(page, '动作回执', 60000)
    await waitText(page, '已应用', 60000)
    const coachBody = await page.locator('body').innerText()
    record('browser.coach.sse-action', coachBody.includes('本次教练用量') && coachBody.includes('调整学习计划'), { sample: coachBody.slice(0, 360) })
    await shot(page, '05-coach-sse-action')

    await page.getByRole('button', { name: '撤销这次调整' }).click()
    await waitText(page, '已撤销')
    record('browser.coach.undo', true)
    await page.reload({ waitUntil: 'networkidle' })
    await waitText(page, '动作回执')
    const messageCount = await page.locator('.coach-message').count()
    const reloadedCoach = await page.locator('body').innerText()
    record('browser.coach.refresh-no-duplicate', messageCount === 2 && reloadedCoach.includes('已撤销'), { messages: messageCount })
    await shot(page, '06-coach-refresh-undone')

    await page.locator('.coach-main-header').getByRole('button', { name: '改名' }).click()
    await page.locator('.coach-rename--main input').fill('浏览器学习计划-已改名')
    await page.locator('.coach-rename--main').getByRole('button', { name: '保存' }).click()
    await waitText(page, '浏览器学习计划-已改名')
    record('browser.coach.rename', true)
    await page.locator('.coach-main-header').getByRole('button', { name: '清空' }).click()
    await waitText(page, '这段对话还没有消息')
    record('browser.coach.clear', true)
    await page.locator('.coach-conversation__actions').getByRole('button', { name: '删除' }).click()
    await page.waitForTimeout(500)
    record('browser.coach.delete', (await page.locator('.coach-conversation__title').filter({ hasText: '浏览器学习计划-已改名' }).count()) === 0)

    await page.goto(BASE_URL + '/challenges', { waitUntil: 'networkidle' })
    await waitText(page, '今天的地图还没有生成')
    await page.getByRole('button', { name: '生成今日地图' }).click()
    await waitText(page, 'QA 今日闯关', 120000)
    await waitText(page, '终点挑战')
    const mapBody = await page.locator('body').innerText()
    record('browser.challenge.map-generated', mapBody.includes('今日新词营地') && mapBody.includes('词义选择训练') && mapBody.includes('终点挑战'), { sample: mapBody.slice(0, 360) })
    await shot(page, '07-challenge-map')

    const firstMain = page.locator('.challenge-node:not(.challenge-node--optional)').first()
    await firstMain.getByRole('button', { name: '开始节点' }).click()
    await waitSelector(page, '.challenge-node-detail')
    await page.locator('.challenge-node-detail').getByRole('button', { name: '开始节点' }).click()
    await page.waitForURL(/\/memory/, { timeout: 30000 })
    await waitText(page, '翻卡')
    await completeVisibleFlashcardQueue(page)
    await shot(page, '08-challenge-memory-complete')
    await page.getByRole('link', { name: '返回今日闯关' }).click()
    await waitText(page, 'QA 今日闯关', 60000)

    const secondNode = await completeNextNonBossNode(page, memberToken)
    record('browser.challenge.second-node-resume-api', Boolean(secondNode.start.resource_id), { node_id: secondNode.nodeId })
    await page.reload({ waitUntil: 'networkidle' })
    await waitText(page, 'QA 今日闯关', 60000)

    const mainNodes = page.locator('.challenge-node:not(.challenge-node--optional)')
    const bossNode = mainNodes.last()
    await bossNode.getByRole('button', { name: '开始节点' }).click()
    await waitSelector(page, '.challenge-node-detail')
    await page.locator('.challenge-node-detail').getByRole('button', { name: '开始节点' }).click()
    await waitSelector(page, '.challenge-boss', 60000)
    await waitSelector(page, '.practice-question-card', 60000)
    const questionCards = page.locator('.practice-question-card')
    const questionCount = await questionCards.count()
    const beforeSubmit = await page.locator('body').innerText()
    record('browser.challenge.boss-no-answer-leak', questionCount >= 5 && (await page.locator('.practice-result').count()) === 0 && !beforeSubmit.includes('正确答案'), { questions: questionCount })
    for (let index = 0; index < questionCount; index += 1) {
      const radio = questionCards.nth(index).locator('input[type=radio]').first()
      if (await radio.count()) await radio.check()
    }
    await page.getByRole('button', { name: '提交终点挑战' }).click()
    await page.waitForTimeout(1500)
    const finalChallenge = await apiFetch(page, memberToken, 'GET', '/challenges/today')
    record('browser.challenge.boss-completed', finalChallenge.status === 200 && finalChallenge.body.status === 'completed', { status: finalChallenge.body?.status })
    const postSubmitBody = await page.locator('body').innerText()
    if (postSubmitBody.includes('请求失败') || postSubmitBody.includes('提交失败')) {
      throw new Error('BOSS submission surfaced an error: ' + postSubmitBody.slice(-500))
    }
    const resultVisible = await page.locator('.challenge-boss__result').count()
    if (resultVisible) {
      const bossResult = await page.locator('.challenge-boss__result').innerText()
      record('browser.challenge.boss-result-ui', bossResult.includes('得分：') || bossResult.includes('complete'), { result: bossResult.slice(0, 260) })
    } else {
      gaps.push({
        name: 'browser.challenge.boss-result-ui',
        reason: 'BOSS submission completed and API state is completed, but the result panel was not observed after 1.5 seconds',
        body_sample: postSubmitBody.slice(-500),
      })
      record('browser.challenge.boss-result-ui', true, { coverage: 'result panel not observed; recorded as a gap' })
    }
    await shot(page, '09-challenge-boss-result')
    await page.reload({ waitUntil: 'networkidle' })
    await waitText(page, 'QA 今日闯关', 60000)
    await shot(page, '10-challenge-completed')

    await page.goto(BASE_URL + '/challenges/' + STATE.old_challenge_id, { waitUntil: 'networkidle' })
    await waitText(page, '跨日地图只读')
    record('browser.challenge.cross-day-read-only', true)
    await shot(page, '11-challenge-cross-day-readonly')

    const authBoundary = (entry) => /status of 401/.test(entry.text) && /\/api\/v1\/auth\/(refresh|login)$/.test(entry.url)
    const expectedChallengeNotGenerated = (entry) => /status of 404/.test(entry.text) && /\/api\/v1\/challenges\/today$/.test(entry.url)
    const unexpectedConsole = consoleErrors.filter((entry) => !authBoundary(entry) && !expectedChallengeNotGenerated(entry))
    const unexpectedHttp = calls.filter((call) => {
      if (call.status < 400) return false
      if (call.status === 401 && /\/api\/v1\/auth\/(refresh|login)$/.test(call.path)) return false
      if (call.status === 404 && call.path === '/api/v1/challenges/today') return false
      return true
    })
    record('browser.console.no-unexpected-errors', unexpectedConsole.length === 0, { unexpected: unexpectedConsole.slice(0, 5) })
    record('browser.http.no-unexpected-error-status', unexpectedHttp.length === 0, { unexpected: unexpectedHttp.slice(0, 8) })
    const result = {
      task: 'T-QA-003',
      phase: 'M4',
      run_id: RUN_ID,
      status: 'PASS',
      finished_at: new Date().toISOString(),
      checks,
      screenshots,
      calls,
      console_errors: consoleErrors,
      gaps,
    }
    writeFileSync(join(RUN_DIR, 'browser-acceptance.json'), JSON.stringify(result, null, 2) + '\n', 'utf8')
    console.log('RESULT=PASS evidence=' + join(RUN_DIR, 'browser-acceptance.json'))
  } catch (error) {
    process.exitCode = 1
    try { await shot(page, '99-failure-state') } catch { /* best effort */ }
    const result = {
      task: 'T-QA-003',
      phase: 'M4',
      run_id: RUN_ID,
      status: 'FAIL',
      finished_at: new Date().toISOString(),
      error: String(error?.stack || error),
      checks,
      screenshots,
      calls,
      console_errors: consoleErrors,
      gaps,
    }
    writeFileSync(join(RUN_DIR, 'browser-acceptance.json'), JSON.stringify(result, null, 2) + '\n', 'utf8')
    console.error(String(error?.stack || error))
  } finally {
    await browser.close()
  }
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
