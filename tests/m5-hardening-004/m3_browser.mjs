#!/usr/bin/env node
/** T-QA-002 M3 real-browser admin/member acceptance. */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const STATE = JSON.parse(readFileSync(process.env.M3_STATE, 'utf8'))
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
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

function record(name, ok, detail = {}) {
  const status = ok ? 'PASS' : 'FAIL'
  checks.push({ name, status, detail })
  console.log(`[${status}] ${name} ${JSON.stringify(detail).slice(0, 400)}`)
  if (!ok) throw new Error(`CHECK FAILED: ${name}`)
}

async function waitText(page, text, timeout = 30000) {
  const end = Date.now() + timeout
  while (Date.now() < end) {
    const body = await page.locator('body').innerText().catch(() => '')
    if (body.includes(text)) return body
    await sleep(150)
  }
  throw new Error(`Text not found: ${text}`)
}

async function shot(page, name) {
  const path = join(SHOT_DIR, `${name}.png`)
  await page.screenshot({ path, fullPage: true })
  screenshots[name] = path
}

async function login(page, username, password) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' })
  await page.fill('#username', username)
  await page.fill('#password', password)
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 20000 }),
    page.getByRole('button', { name: '登录' }).click(),
  ])
  await page.waitForLoadState('networkidle')
}

async function waitPracticeReady(page) {
  const end = Date.now() + 120000
  while (Date.now() < end) {
    const cards = await page.locator('.practice-question-card').count()
    const failedHeading = await page.locator('p.eyebrow').filter({ hasText: '生成失败' }).count()
    if (cards > 0 || failedHeading > 0) {
      return page.locator('body').innerText()
    }
    await sleep(300)
  }
  throw new Error('practice session did not become ready/failed')
}

async function main() {
  const browser = await chromium.launch({ executablePath: EDGE, headless: true })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'zh-CN' })
  const page = await context.newPage()
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push({ text: message.text().slice(0, 300), url: message.location()?.url || '' })
  })
  page.on('pageerror', (error) => consoleErrors.push({ text: String(error).slice(0, 300), url: 'pageerror' }))
  page.on('response', (response) => {
    const url = response.url()
    if (!url.includes('/api/v1/')) return
    calls.push({ method: response.request().method(), path: new URL(url).pathname, status: response.status(), request_id: response.headers()['x-request-id'] || null })
  })
  try {
    await login(page, STATE.admin.username, STATE.admin.password)
    record('browser.admin.login', !page.url().includes('/login'), { url: page.url() })

    await page.goto(`${BASE_URL}/admin/ai/providers`, { waitUntil: 'networkidle' })
    await waitText(page, 'AI 提供商')
    await waitText(page, STATE.provider_name)
    const providerBody = await page.locator('body').innerText()
    record('browser.admin.provider-masked', providerBody.includes('sk-****') && !providerBody.includes(STATE.provider_key), { provider: STATE.provider_name })
    await page.getByRole('button', { name: '连接检查' }).first().click()
    await waitText(page, '真实连接检查成功')
    record('browser.admin.provider-real-connection', true)
    await shot(page, '01-admin-provider')

    await page.goto(`${BASE_URL}/admin/ai/prompts`, { waitUntil: 'networkidle' })
    await waitText(page, 'AI 提示词')
    await page.getByRole('button', { name: /practice_generation/ }).click()
    await page.waitForSelector('#prompt-template')
    await page.fill('#prompt-template', 'T-QA-002 browser-controlled prompt. Return strict JSON only.')
    await page.getByRole('button', { name: '覆盖保存' }).click()
    await waitText(page, '已保存')
    record('browser.admin.prompt-overwrite', true)
    await shot(page, '02-admin-prompt')

    await context.clearCookies()
    await login(page, STATE.member_ui.username, STATE.member_ui.password)
    record('browser.member.login', !page.url().includes('/login'), { url: page.url() })
    await page.goto(`${BASE_URL}/practice`, { waitUntil: 'networkidle' })
    await waitText(page, 'AI 练习')
    await page.getByRole('button', { name: /填空/ }).click()
    await page.selectOption('#practice-source', 'whole_book')
    await page.selectOption('#practice-count', '3')
    await page.selectOption('#practice-wordbook', STATE.wordbook.id)
    await page.getByRole('button', { name: '生成练习' }).click()
    await page.waitForURL(/\/practice\/[0-9a-f-]+/, { timeout: 30000 })
    const readyText = await waitPracticeReady(page)
    record('browser.practice.real-generation', readyText.includes('作答进度'), { url: page.url() })
    record('browser.practice.no-answer-before-submit', (await page.locator('.practice-result').count()) === 0 && (await page.locator('.result-question').count()) === 0, { sample: readyText.slice(0, 240) })
    await page.getByRole('button', { name: '保存草稿' }).click()
    await waitText(page, '草稿已保存')
    await page.reload({ waitUntil: 'networkidle' })
    await waitPracticeReady(page)
    const cards = page.locator('.practice-question-card')
    const cardCount = await cards.count()
    for (let index = 0; index < cardCount; index += 1) {
      const firstChoice = cards.nth(index).locator('input[type=radio]').first()
      if (await firstChoice.count()) await firstChoice.check()
    }
    await page.getByRole('button', { name: '提交全部答案' }).click()
    await waitText(page, '本次练习结果')
    const resultText = await page.locator('body').innerText()
    record('browser.practice.submit-and-result', resultText.includes('服务端评分结果') && resultText.includes('正确答案'), { cards: cardCount })
    await shot(page, '03-practice-result')

    await page.goto(`${BASE_URL}/practice/${STATE.failed_session_id}`, { waitUntil: 'networkidle' })
    await waitText(page, '生成失败')
    const failureText = await page.locator('body').innerText()
    record('browser.practice.failure-state', failureText.includes('重新生成') && failureText.includes('新建练习'), { sample: failureText.slice(0, 260) })
    await shot(page, '04-practice-failure')

    await page.goto(`${BASE_URL}/notifications`, { waitUntil: 'networkidle' })
    await waitText(page, '通知中心')
    const notificationItems = page.locator('.notification-item')
    record('browser.notifications.real-inbox', (await notificationItems.count()) > 0, { count: await notificationItems.count() })
    const markRead = page.getByRole('button', { name: '标记已读', exact: true }).first()
    if (await markRead.count()) {
      await markRead.click()
      await waitText(page, '服务端已确认该通知为已读')
    }
    await shot(page, '05-notifications')

    await page.goto(`${BASE_URL}/notifications/preferences`, { waitUntil: 'networkidle' })
    await waitText(page, '通知偏好')
    record('browser.notifications.preferences', (await page.locator('.notification-category-option').count()) === 7, { categories: await page.locator('.notification-category-option').count() })
    await shot(page, '06-notification-preferences')

    const authBoundary = (entry) => /status of 401/.test(entry.text) && /\/api\/v1\/auth\/(refresh|login)$/.test(entry.url)
    const unexpectedConsole = consoleErrors.filter((entry) => !authBoundary(entry))
    const unexpectedHttp = calls.filter((call) => call.status >= 400 && !(call.status === 401 && /\/api\/v1\/auth\/(refresh|login)$/.test(call.path)))
    record('browser.console.no-unexpected-errors', unexpectedConsole.length === 0, { unexpected: unexpectedConsole.slice(0, 5) })
    record('browser.http.no-unexpected-error-status', unexpectedHttp.length === 0, { unexpected: unexpectedHttp.slice(0, 8) })
    const result = { task: 'T-QA-002', phase: 'M3', run_id: RUN_ID, status: 'PASS', finished_at: new Date().toISOString(), checks, screenshots, calls, console_errors: consoleErrors }
    writeFileSync(join(RUN_DIR, 'browser-acceptance.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8')
    console.log(`RESULT=PASS evidence=${join(RUN_DIR, 'browser-acceptance.json')}`)
  } catch (error) {
    process.exitCode = 1
    try { await shot(page, '99-failure-state') } catch { /* best effort */ }
    const result = { task: 'T-QA-002', phase: 'M3', run_id: RUN_ID, status: 'FAIL', finished_at: new Date().toISOString(), error: String(error?.stack || error), checks, screenshots, calls, console_errors: consoleErrors }
    writeFileSync(join(RUN_DIR, 'browser-acceptance.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8')
    console.error(String(error?.stack || error))
  } finally {
    await browser.close()
  }
}

main().catch((error) => { console.error(error); process.exit(1) })
