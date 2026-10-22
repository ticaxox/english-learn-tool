#!/usr/bin/env node
/**
 * Verify that the real browser UI fails closed when the API is unavailable.
 * The frontend preview must remain reachable while the backend is stopped.
 */

import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const BASE_URL = (process.env.BROWSER_BASE_URL || 'http://127.0.0.1:4173').replace(/\/+$/, '')
const EVIDENCE_DIR = process.env.EVIDENCE_DIR ? path.resolve(process.env.EVIDENCE_DIR) : null
const PLAYWRIGHT_CORE_PATH = process.env.PLAYWRIGHT_CORE_PATH
const CHROME_EXECUTABLE_PATH =
  process.env.CHROME_EXECUTABLE_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const RUN_ID = process.env.BROWSER_RUN_ID || `a30-browser-failure-${Date.now()}`
const PHASE_TIMEOUT_MS = Number(process.env.BROWSER_PHASE_TIMEOUT_MS || 15_000)

if (!EVIDENCE_DIR) throw new Error('EVIDENCE_DIR is required')
if (!PLAYWRIGHT_CORE_PATH) throw new Error('PLAYWRIGHT_CORE_PATH is required')

const { chromium } = await import(pathToFileURL(path.join(PLAYWRIGHT_CORE_PATH, 'index.mjs')).href)

const checks = []
const network = []
const pageErrors = []
const startedAt = new Date().toISOString()

function check(name, passed, details = {}) {
  checks.push({ name, status: passed ? 'PASS' : 'FAIL', details })
  console.log(`[${passed ? 'PASS' : 'FAIL'}] ${name}`)
}

let browser
try {
  await mkdir(path.join(EVIDENCE_DIR, 'screenshots'), { recursive: true })
  browser = await chromium.launch({
    headless: process.env.BROWSER_HEADLESS !== 'false',
    executablePath: CHROME_EXECUTABLE_PATH,
  })
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const page = await context.newPage()

  page.on('pageerror', (error) => pageErrors.push(String(error)))
  page.on('requestfailed', (request) => {
    const url = new URL(request.url())
    if (url.pathname.startsWith('/api/v1/')) {
      network.push({
        event: 'requestfailed',
        method: request.method(),
        path: url.pathname,
        error: request.failure()?.errorText || null,
      })
    }
  })
  page.on('response', (response) => {
    const url = new URL(response.url())
    if (url.pathname.startsWith('/api/v1/')) {
      network.push({
        event: 'response',
        method: response.request().method(),
        path: url.pathname,
        status: response.status(),
        request_id: response.headers()['x-request-id'] || null,
      })
    }
  })

  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded', timeout: PHASE_TIMEOUT_MS })
  await page.getByRole('heading', { name: '登录学习空间' }).waitFor({ timeout: PHASE_TIMEOUT_MS })
  await page.getByLabel('用户名').fill('qa_api_unavailable_probe')
  await page.getByLabel('密码').fill('Not-A-Real-Password-9!')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.waitForTimeout(1_500)

  const alert = page.getByRole('alert').first()
  const alertVisible = await alert.isVisible().catch(() => false)
  const alertText = alertVisible ? (await alert.innerText()).trim() : ''
  const finalPath = new URL(page.url()).pathname
  const loginResponses = network.filter((item) => item.event === 'response' && item.path === '/api/v1/auth/login')
  const successfulLoginResponses = loginResponses.filter((item) => item.status >= 200 && item.status < 300)
  const loginRequestFailures = network.filter(
    (item) => item.event === 'requestfailed' && item.path === '/api/v1/auth/login',
  )
  const storage = await page.evaluate(() => ({
    local: Object.fromEntries(Object.entries(localStorage)),
    session: Object.fromEntries(Object.entries(sessionStorage)),
    cookies: document.cookie,
  }))
  const storageHasAccessToken = JSON.stringify(storage).toLowerCase().includes('access_token')
  const cookieHasSessionToken = /(?:^|;\s*)refresh_token=/.test(storage.cookies)

  check('API unavailable: backend login succeeds zero times', successfulLoginResponses.length === 0, {
    login_responses: loginResponses,
  })
  check('API unavailable: a real login transport/proxy failure was observed', loginRequestFailures.length > 0 || loginResponses.length > 0, {
    request_failures: loginRequestFailures,
    login_responses: loginResponses,
  })
  check('API unavailable: user remains on login route', finalPath === '/login', { final_path: finalPath })
  check('API unavailable: visible error replaces any success state', alertVisible && alertText.length > 0, {
    alert_text: alertText,
  })
  check('API unavailable: no success wording is shown', !/(登录成功|已完成认证)/.test(alertText), {
    alert_text: alertText,
  })
  check('API unavailable: access token is not persisted in web storage', !storageHasAccessToken, {
    local_storage_keys: Object.keys(storage.local),
    session_storage_keys: Object.keys(storage.session),
  })
  check('API unavailable: refresh cookie is not present', !cookieHasSessionToken, {
    cookie_names: storage.cookies.split(';').map((item) => item.trim().split('=')[0]).filter(Boolean),
  })

  await page.screenshot({
    path: path.join(EVIDENCE_DIR, 'screenshots', '01-api-unavailable-login.png'),
    fullPage: true,
    mask: [page.getByLabel('密码')],
    maskColor: '#d7dde8',
  })

  await context.close()
} catch (error) {
  check('browser failure-state probe completes', false, {
    error: `${error?.name || 'Error'}: ${error?.message || String(error)}`,
  })
} finally {
  if (browser) await browser.close()
}

const result = {
  run_id: RUN_ID,
  scenario: 'api-unavailable',
  started_at: startedAt,
  finished_at: new Date().toISOString(),
  base_url: BASE_URL,
  status: checks.length > 0 && checks.every((item) => item.status === 'PASS') ? 'PASS' : 'FAIL',
  checks,
  network,
  page_errors: pageErrors,
  screenshots: checks.length > 0 ? ['screenshots/01-api-unavailable-login.png'] : [],
}
const outputPath = path.join(EVIDENCE_DIR, 'browser-failure-result.json')
await writeFile(outputPath, `${JSON.stringify(result, null, 2)}\n`, 'utf8')
console.log(`RESULT=${outputPath}`)
process.exit(result.status === 'PASS' ? 0 : 1)
