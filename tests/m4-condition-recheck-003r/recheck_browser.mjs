#!/usr/bin/env node
/** Focused T-QA-003R browser recheck: dashboard scope and BOSS completion. */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const STATE = JSON.parse(readFileSync(process.env.RECHECK_STATE, 'utf8'))
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

async function applyDashboard(page, group, expected) {
  await page.fill('#dashboard-department', 'QA')
  await page.fill('#dashboard-group', group)
  await page.getByRole('button', { name: '应用筛选' }).click()
  return waitText(page, expected, 30000)
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
    await applyDashboard(page, 'NoMembers', '当前筛选范围内没有成员')
    let body = await page.locator('body').innerText()
    record('browser.dashboard.zero-member-empty', body.includes('当前筛选范围内没有成员') && !body.includes('聚合结果已按隐私规则抑制'))
    await shot(page, '01-dashboard-zero-member')

    await applyDashboard(page, 'Single', '聚合结果已按隐私规则抑制')
    body = await page.locator('body').innerText()
    record('browser.dashboard.one-member-suppressed', body.includes('聚合结果已按隐私规则抑制'), { sample: body.slice(-360) })
    await shot(page, '02-dashboard-one-member-privacy')

    await applyDashboard(page, 'Small', '聚合结果已按隐私规则抑制')
    record('browser.dashboard.two-member-suppressed', true)
    await shot(page, '03-dashboard-two-member-privacy')

    await applyDashboard(page, 'Core', '组织成员')
    body = await page.locator('body').innerText()
    record('browser.dashboard.three-member-aggregate', body.includes('组织成员') && !body.includes('聚合结果已按隐私规则抑制'))
    await shot(page, '04-dashboard-core-aggregate')

    await context.clearCookies()
    await login(page, STATE.member_ui.username, STATE.member_ui.password)
    record('browser.member.login', !page.url().includes('/login'), { url: page.url() })

    await page.goto(BASE_URL + '/coach', { waitUntil: 'networkidle' })
    await waitText(page, 'AI 教练工作区')
    await page.getByRole('button', { name: '新建', exact: true }).click()
    await page.locator('input[placeholder="例如：本周学习计划"]').fill('T-QA-003R coach regression')
    await page.getByRole('button', { name: '创建对话' }).click()
    await waitText(page, 'T-QA-003R coach regression')
    await page.locator('#coach-message-input').fill('请调整今日计划：25 个新词，45 分钟。')
    await page.getByRole('button', { name: '发送消息' }).click()
    await waitText(page, '动作回执', 60000)
    body = await page.locator('body').innerText()
    record('browser.coach.sse-action-regression', body.includes('动作回执') && body.includes('本次教练用量'), { sample: body.slice(-320) })
    await page.getByRole('button', { name: '撤销这次调整' }).click()
    await waitText(page, '已撤销')
    await page.reload({ waitUntil: 'networkidle' })
    await waitText(page, '动作回执')
    record('browser.coach.undo-refresh-regression', (await page.locator('.coach-message').count()) === 2)
    await shot(page, '05-coach-regression')

    await page.goto(BASE_URL + '/challenges/' + STATE.challenge_id, { waitUntil: 'networkidle' })
    await waitText(page, 'QA 今日闯关', 60000)
    const mainNodes = page.locator('.challenge-node:not(.challenge-node--optional)')
    const bossNode = mainNodes.last()
    await bossNode.getByRole('button', { name: '继续任务' }).click()
    await waitSelector(page, '.challenge-node-detail')
    await page.locator('.challenge-node-detail').getByRole('button', { name: '继续节点' }).click()
    await waitSelector(page, '.challenge-boss', 60000)
    await waitSelector(page, '.practice-question-card', 60000)
    const questions = page.locator('.practice-question-card')
    const questionCount = await questions.count()
    const beforeSubmit = await page.locator('body').innerText()
    record('browser.boss-answer-safety', questionCount >= 5 && !beforeSubmit.includes('正确答案'))
    for (let index = 0; index < questionCount; index += 1) {
      const radio = questions.nth(index).locator('input[type=radio]').first()
      if (await radio.count()) await radio.check()
    }
    await page.getByRole('button', { name: '提交终点挑战' }).click()
    await waitSelector(page, '.challenge-boss__result', 60000)
    const resultBody = await page.locator('.challenge-boss__result').innerText()
    record('browser.boss-completed-result-visible', resultBody.includes('终点挑战已完成') && resultBody.includes('得分'), { result: resultBody.slice(0, 300) })
    await shot(page, '06-boss-result-visible')

    await page.reload({ waitUntil: 'networkidle' })
    await waitText(page, 'QA 今日闯关', 60000)
    body = await page.locator('body').innerText()
    record('browser.boss-refresh-completed-state', body.includes('主线 3 / 3') && !body.includes('0 / 5 题已作答'), { sample: body.slice(-420) })
    await shot(page, '07-boss-refreshed-map')

    await page.locator('.challenge-node:not(.challenge-node--optional)').last().getByRole('button', { name: '查看结果' }).click()
    await waitSelector(page, '.challenge-node-detail')
    await page.locator('.challenge-node-detail').getByRole('button', { name: '查看节点结果' }).click()
    await page.waitForURL(/\/practice\/[0-9a-f-]+/, { timeout: 30000 })
    await waitText(page, '本次练习结果', 60000)
    record('browser.boss-reenter-completed-result', true, { url: page.url() })
    await shot(page, '08-boss-reenter-result')

    const expectedConsole = (entry) => /status of 401/.test(entry.text) && /\/api\/v1\/auth\/(refresh|login)$/.test(entry.url)
    const unexpectedConsole = consoleErrors.filter((entry) => !expectedConsole(entry))
    const unexpectedHttp = calls.filter((call) => call.status >= 400 && !(call.status === 401 && /\/api\/v1\/auth\/(refresh|login)$/.test(call.path)))
    record('browser.console.no-unexpected-errors', unexpectedConsole.length === 0, { unexpected: unexpectedConsole.slice(0, 5) })
    record('browser.http.no-unexpected-error-status', unexpectedHttp.length === 0, { unexpected: unexpectedHttp.slice(0, 8) })
    const result = {
      task: 'T-QA-003R', phase: 'M4R', run_id: RUN_ID, status: 'PASS',
      finished_at: new Date().toISOString(), checks, screenshots, calls, console_errors: consoleErrors, gaps,
    }
    writeFileSync(join(RUN_DIR, 'browser-acceptance.json'), JSON.stringify(result, null, 2) + '\n', 'utf8')
    console.log('RESULT=PASS evidence=' + join(RUN_DIR, 'browser-acceptance.json'))
  } catch (error) {
    process.exitCode = 1
    try { await shot(page, '99-failure-state') } catch { /* best effort */ }
    const result = {
      task: 'T-QA-003R', phase: 'M4R', run_id: RUN_ID, status: 'FAIL',
      finished_at: new Date().toISOString(), error: String(error?.stack || error),
      checks, screenshots, calls, console_errors: consoleErrors, gaps,
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
