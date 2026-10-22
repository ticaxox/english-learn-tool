#!/usr/bin/env node
/**
 * Live AUTH-INT-001 browser acceptance runner.
 *
 * It uses a fresh isolated backend database, a real Chromium browser, and only
 * generated test accounts. Secrets are kept in memory and masked from screenshots.
 */

import { randomBytes } from 'node:crypto'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const BASE_URL = (process.env.BROWSER_BASE_URL || 'http://127.0.0.1:4173').replace(/\/+$/, '')
const API_BASE_URL = (process.env.API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '')
const ADMIN_USERNAME = process.env.BROWSER_ADMIN_USERNAME
const ADMIN_INITIAL_PASSWORD = process.env.BROWSER_ADMIN_PASSWORD
const NEW_ADMIN_PASSWORD = process.env.BROWSER_NEW_ADMIN_PASSWORD || strongPassword('BrowserAdmin')
const EVIDENCE_DIR = process.env.EVIDENCE_DIR ? path.resolve(process.env.EVIDENCE_DIR) : null
const PLAYWRIGHT_CORE_PATH = process.env.PLAYWRIGHT_CORE_PATH
const CHROME_EXECUTABLE_PATH =
  process.env.CHROME_EXECUTABLE_PATH ||
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const HEADLESS = process.env.BROWSER_HEADLESS !== 'false'
const RUN_ID = process.env.BROWSER_RUN_ID || `a30-browser-${Date.now()}`
const PHASE_TIMEOUT_MS = Number(process.env.BROWSER_PHASE_TIMEOUT_MS || 20_000)

if (!EVIDENCE_DIR) throw new Error('EVIDENCE_DIR is required')
if (!PLAYWRIGHT_CORE_PATH) throw new Error('PLAYWRIGHT_CORE_PATH is required')
if (!ADMIN_USERNAME) throw new Error('BROWSER_ADMIN_USERNAME is required')
if (!ADMIN_INITIAL_PASSWORD) throw new Error('BROWSER_ADMIN_PASSWORD is required')

const playwrightEntry = path.join(PLAYWRIGHT_CORE_PATH, 'index.mjs')
const { chromium } = await import(pathToFileURL(playwrightEntry).href)

class CheckFailure extends Error {}

class Evidence {
  constructor() {
    this.checks = []
    this.network = []
    this.screenshots = []
    this.startedAt = new Date().toISOString()
  }

  check(name, passed, details = {}) {
    const entry = { name, status: passed ? 'PASS' : 'FAIL', details }
    this.checks.push(entry)
    console.log(`[${entry.status}] ${name}`)
    if (!passed) throw new CheckFailure(`${name}: ${JSON.stringify(details)}`)
  }

  async screenshot(page, name, masks = []) {
    const file = path.join(EVIDENCE_DIR, 'screenshots', `${name}.png`)
    await page.screenshot({ path: file, fullPage: true, mask: masks, maskColor: '#d7dde8' })
    this.screenshots.push(path.relative(EVIDENCE_DIR, file).replaceAll('\\', '/'))
  }

  finish(error = null) {
    return {
      run_id: RUN_ID,
      started_at: this.startedAt,
      finished_at: new Date().toISOString(),
      base_url: BASE_URL,
      api_base_url: API_BASE_URL,
      browser: 'Chromium',
      status: error || this.checks.some((item) => item.status === 'FAIL') ? 'FAIL' : 'PASS',
      error,
      checks: this.checks,
      network: this.network,
      screenshots: this.screenshots,
    }
  }
}

const evidence = new Evidence()
const sensitiveKeys = new Set([
  'answers',
  'draft',
  'coach_message',
  'coach_title',
  'coach_body',
  'wordbook_content',
])
const secretKeys = new Set(['access_token', 'refresh_token', 'temporary_password'])

function strongPassword(prefix) {
  return `${prefix}-${randomBytes(15).toString('base64url')}-9!z`
}

function summarizeBody(value) {
  if (!value || typeof value !== 'object') return { body_type: typeof value }
  const keys = new Set()
  const sensitiveHits = new Set()
  const secretFields = new Set()
  const visit = (node, depth = 0) => {
    if (depth > 8 || !node || typeof node !== 'object') return
    if (Array.isArray(node)) {
      for (const item of node.slice(0, 20)) visit(item, depth + 1)
      return
    }
    for (const [key, child] of Object.entries(node)) {
      if (depth === 0) keys.add(key)
      if (sensitiveKeys.has(key)) sensitiveHits.add(key)
      if (secretKeys.has(key)) secretFields.add(key)
      visit(child, depth + 1)
    }
  }
  visit(value)
  return {
    keys: [...keys].sort(),
    sensitive_key_hits: [...sensitiveHits].sort(),
    secret_value_fields_present: [...secretFields].sort(),
  }
}

function monitorContext(context, label) {
  context.on('response', (response) => {
    const request = response.request()
    let url
    try {
      url = new URL(response.url())
    } catch {
      return
    }
    if (!url.pathname.startsWith('/api/v1/')) return
    const entry = {
      context: label,
      method: request.method(),
      path: url.pathname,
      status: response.status(),
      request_id: response.headers()['x-request-id'] || null,
      set_cookie_names: (response.headers()['set-cookie'] || '')
        .split(/,(?=[^;]+?=)/)
        .map((header) => header.split('=', 1)[0].trim())
        .filter(Boolean),
      body: null,
    }
    evidence.network.push(entry)
    response
      .json()
      .then((body) => {
        entry.body = summarizeBody(body)
      })
      .catch(() => {
        entry.body = { body_type: 'non-json' }
      })
  })
}

function isLogin(response) {
  return response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/auth/login'
}

function isRefresh(response) {
  return response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/auth/refresh'
}

function isLogout(response) {
  return response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/auth/logout'
}

async function storageLeakCheck(page, label, accessToken) {
  const snapshot = await page.evaluate(() => ({
    localKeys: Object.keys(localStorage),
    sessionKeys: Object.keys(sessionStorage),
    localValues: Object.values(localStorage),
    sessionValues: Object.values(sessionStorage),
  }))
  const values = [...snapshot.localValues, ...snapshot.sessionValues, ...snapshot.localKeys, ...snapshot.sessionKeys]
  const hasTokenKey = values.some((value) => /access[_-]?token|refresh[_-]?token/i.test(String(value)))
  const hasTokenValue = Boolean(accessToken) && values.some((value) => String(value).includes(accessToken))
  evidence.check(`${label}: access token is absent from browser storage`, !hasTokenKey && !hasTokenValue, {
    local_key_count: snapshot.localKeys.length,
    session_key_count: snapshot.sessionKeys.length,
    token_value_present: hasTokenValue,
  })
}

async function cookieChecks(context, label) {
  const cookies = await context.cookies()
  const refresh = cookies.find((cookie) => cookie.name === 'refresh_token')
  const csrf = cookies.find((cookie) => cookie.name === 'csrf_token')
  evidence.check(`${label}: HttpOnly refresh cookie present`, Boolean(refresh?.httpOnly), {
    path: refresh?.path,
    same_site: refresh?.sameSite,
  })
  evidence.check(`${label}: readable CSRF cookie present`, Boolean(csrf) && csrf.httpOnly === false, {
    path: csrf?.path,
    same_site: csrf?.sameSite,
  })
}

async function gotoPath(page, pathname) {
  await page.goto(`${BASE_URL}${pathname}`, { waitUntil: 'domcontentloaded', timeout: PHASE_TIMEOUT_MS })
}

async function loginThroughUi(page, username, password) {
  await page.locator('#username').fill(username)
  await page.locator('#password').fill(password)
  const responsePromise = page.waitForResponse(isLogin, { timeout: PHASE_TIMEOUT_MS })
  await page.getByRole('button', { name: '登录', exact: true }).click()
  return responsePromise
}

async function changePasswordThroughUi(page, oldPassword, newPassword, expectedInitialPath = '/change-password') {
  await page.waitForURL(`**${expectedInitialPath}`, { timeout: PHASE_TIMEOUT_MS })
  await page.locator('#old-password').fill(oldPassword)
  await page.locator('#new-password').fill(newPassword)
  await page.locator('#confirm-password').fill(newPassword)
  const responsePromise = page.waitForResponse(isLogin, { timeout: PHASE_TIMEOUT_MS })
  await page.getByRole('button', { name: '保存新密码', exact: true }).click()
  const relogin = await responsePromise
  await page.waitForURL('**/overview', { timeout: PHASE_TIMEOUT_MS })
  return relogin
}

async function main() {
  await mkdir(path.join(EVIDENCE_DIR, 'screenshots'), { recursive: true })
  const browser = await chromium.launch({
    headless: HEADLESS,
    executablePath: CHROME_EXECUTABLE_PATH,
    args: ['--disable-dev-shm-usage'],
  })
  const pageErrors = []
  try {
    const adminContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    monitorContext(adminContext, 'admin')
    const page = await adminContext.newPage()
    page.on('pageerror', (error) => pageErrors.push({ context: 'admin', message: error.message }))

    await gotoPath(page, '/login')
    await page.getByRole('heading', { name: '登录学习空间' }).waitFor()
    const adminLogin = await loginThroughUi(page, ADMIN_USERNAME, ADMIN_INITIAL_PASSWORD)
    evidence.check('first administrator login uses the real API', adminLogin.status() === 200, {
      status: adminLogin.status(),
      request_id: adminLogin.headers()['x-request-id'] || null,
    })
    const initialAdminSession = await adminLogin.json()
    const initialAdminToken = initialAdminSession.access_token
    evidence.check('first administrator is forced to change the initial password', initialAdminSession.user?.must_change_password === true)
    await page.waitForURL('**/change-password', { timeout: PHASE_TIMEOUT_MS })
    await storageLeakCheck(page, 'forced password change', initialAdminToken)
    await cookieChecks(adminContext, 'forced password change')
    await evidence.screenshot(page, '01-admin-forced-password-change')

    await gotoPath(page, '/admin/users')
    await page.waitForURL('**/change-password', { timeout: PHASE_TIMEOUT_MS })
    evidence.check('route guard blocks admin APIs before forced password change', new URL(page.url()).pathname === '/change-password')

    const adminRelogin = await changePasswordThroughUi(page, ADMIN_INITIAL_PASSWORD, NEW_ADMIN_PASSWORD)
    const adminSession = await adminRelogin.json()
    const adminToken = adminSession.access_token
    evidence.check('administrator relogin after password change succeeds', adminSession.user?.must_change_password === false, {
      request_id: adminRelogin.headers()['x-request-id'] || null,
    })
    await storageLeakCheck(page, 'admin authenticated session', adminToken)
    await page.getByRole('heading', { name: '学习概览' }).waitFor()
    await evidence.screenshot(page, '02-admin-overview-after-change')

    const refreshResponsePromise = page.waitForResponse(isRefresh, { timeout: PHASE_TIMEOUT_MS })
    await page.reload({ waitUntil: 'domcontentloaded' })
    const refreshed = await refreshResponsePromise
    evidence.check('page reload restores the session through HttpOnly refresh cookie', refreshed.status() === 200, {
      status: refreshed.status(),
      request_id: refreshed.headers()['x-request-id'] || null,
    })
    const refreshBody = await refreshed.json()
    await page.getByRole('heading', { name: '学习概览' }).waitFor()
    await storageLeakCheck(page, 'session restored after reload', refreshBody.access_token)
    await evidence.screenshot(page, '03-session-restored-after-reload')

    await page.getByRole('link', { name: '成员管理', exact: true }).click()
    await page.waitForURL('**/admin/users', { timeout: PHASE_TIMEOUT_MS })
    await page.getByRole('heading', { name: '成员管理', exact: true }).waitFor()

    const suffix = randomBytes(4).toString('hex')
    const memberUsername = `qa_browser_${suffix}`
    const memberInitialPassword = strongPassword('MemberInit')
    const memberSecondPassword = strongPassword('MemberNext')
    await page.getByRole('button', { name: '添加成员', exact: true }).click()
    await page.locator('#create-username').fill(memberUsername)
    await page.locator('#create-display-name').fill('A30 Browser Member')
    await page.locator('#create-department').fill('QA')
    await page.locator('#create-learning-group').fill('Browser')
    await page.getByLabel('由管理员填写').check()
    await page.locator('#create-password').fill(memberInitialPassword)
    const createResponsePromise = page.waitForResponse(
      (response) => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/admin/users',
      { timeout: PHASE_TIMEOUT_MS },
    )
    await page.getByRole('button', { name: '创建成员', exact: true }).click()
    const created = await createResponsePromise
    evidence.check('administrator creates a member through the real UI', created.status() === 201, {
      status: created.status(),
      request_id: created.headers()['x-request-id'] || null,
    })
    const temporaryDialog = page.getByRole('dialog', { name: '一次性临时密码' })
    await page.getByRole('button', { name: '收起创建表单', exact: true }).click()
    await page.locator('#member-search').fill(memberUsername)
    await page.getByRole('button', { name: '筛选', exact: true }).click()
    await page.locator('.member-table tbody tr').filter({ hasText: `@${memberUsername}` }).waitFor()
    await evidence.screenshot(page, '04-member-created-and-filtered')

    const memberContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
    monitorContext(memberContext, 'member')
    const memberPage = await memberContext.newPage()
    memberPage.on('pageerror', (error) => pageErrors.push({ context: 'member', message: error.message }))
    await gotoPath(memberPage, '/login')
    const memberLogin = await loginThroughUi(memberPage, memberUsername, memberInitialPassword)
    evidence.check('member first login uses the real API', memberLogin.status() === 200)
    const memberLoginBody = await memberLogin.json()
    evidence.check('member first login forces password change', memberLoginBody.user?.must_change_password === true)
    await memberPage.waitForURL('**/change-password', { timeout: PHASE_TIMEOUT_MS })
    await storageLeakCheck(memberPage, 'member forced password change', memberLoginBody.access_token)
    await evidence.screenshot(memberPage, '05-member-forced-password-change')

    await gotoPath(memberPage, '/admin/users')
    await memberPage.waitForURL('**/change-password', { timeout: PHASE_TIMEOUT_MS })
    evidence.check('member cannot bypass forced password change through direct URL', new URL(memberPage.url()).pathname === '/change-password')

    const memberRelogin = await changePasswordThroughUi(memberPage, memberInitialPassword, memberSecondPassword)
    const memberSession = await memberRelogin.json()
    evidence.check('member relogin after password change succeeds', memberSession.user?.must_change_password === false)
    await gotoPath(memberPage, '/admin/users')
    await memberPage.waitForURL('**/overview?access=denied', { timeout: PHASE_TIMEOUT_MS })
    await memberPage.getByText('当前账号没有访问组织管理页面的权限。').waitFor()
    await evidence.screenshot(memberPage, '06-member-admin-access-denied')

    const memberRow = page.locator('.member-table tbody tr').filter({ hasText: `@${memberUsername}` })
    await memberRow.getByRole('button', { name: '停用', exact: true }).click()
    await page.getByRole('dialog', { name: '确认停用成员' }).getByRole('button', { name: '确认', exact: true }).click()
    await page.getByText(/A30 Browser Member 已停用/).waitFor()
    evidence.check('administrator can disable a member through the UI', true)

    await memberPage.reload({ waitUntil: 'domcontentloaded' })
    await memberPage.waitForURL((url) => url.pathname === '/login', { timeout: PHASE_TIMEOUT_MS })
    evidence.check('member session is revoked after administrator disables the account', new URL(memberPage.url()).pathname === '/login')
    await evidence.screenshot(memberPage, '07-disabled-member-session-revoked')

    await memberRow.getByRole('button', { name: '启用', exact: true }).click()
    await page.getByRole('dialog', { name: '确认启用成员' }).getByRole('button', { name: '确认', exact: true }).click()
    await page.getByText(/A30 Browser Member 已启用/).waitFor()
    evidence.check('administrator can re-enable a member through the UI', true)

    await memberRow.getByRole('button', { name: '重置密码', exact: true }).click()
    await page.getByRole('dialog', { name: '确认重置密码' }).getByRole('button', { name: '确认', exact: true }).click()
    const resetDialog = page.getByRole('dialog', { name: '一次性临时密码' })
    await resetDialog.waitFor()
    const resetPassword = (await resetDialog.locator('.secret-value code').first().innerText()).trim()
    evidence.check('administrator reset returns a one-time password', resetPassword.length >= 12)
    await evidence.screenshot(page, '08-member-password-reset-once', [resetDialog.locator('.secret-value')])
    await resetDialog.getByRole('button', { name: '我已安全保存，关闭' }).click()

    await gotoPath(memberPage, '/login')
    const resetLogin = await loginThroughUi(memberPage, memberUsername, resetPassword)
    evidence.check('member can authenticate with the administrator-generated reset password', resetLogin.status() === 200)
    await memberPage.waitForURL('**/change-password', { timeout: PHASE_TIMEOUT_MS })
    await evidence.screenshot(memberPage, '09-member-forced-change-after-reset')

    await page.locator('#member-search').fill(ADMIN_USERNAME)
    await page.getByRole('button', { name: '筛选', exact: true }).click()
    const adminRow = page.locator('.member-table tbody tr').filter({ hasText: `@${ADMIN_USERNAME}` })
    await adminRow.waitFor()
    await adminRow.getByRole('button', { name: '角色', exact: true }).click()
    const roleDialog = page.getByRole('dialog', { name: '确认修改角色' })
    await roleDialog.locator('#action-role').selectOption('member')
    const demoteResponsePromise = page.waitForResponse(
      (response) => response.request().method() === 'PATCH' && response.url().includes('/api/v1/admin/users/'),
      { timeout: PHASE_TIMEOUT_MS },
    )
    await roleDialog.getByRole('button', { name: '确认', exact: true }).click()
    const demoteResponse = await demoteResponsePromise
    evidence.check('last enabled administrator demotion is rejected', demoteResponse.status() === 409, {
      status: demoteResponse.status(),
      request_id: demoteResponse.headers()['x-request-id'] || null,
    })
    await roleDialog.getByText('LAST_ADMIN_PROTECTED').waitFor()
    await evidence.screenshot(page, '10-last-admin-protection')
    await roleDialog.getByRole('button', { name: '取消', exact: true }).click()

    let interceptedStatusRequests = 0
    await page.route('**/api/v1/admin/users/import/*', async (route) => {
      if (route.request().method() === 'GET' && interceptedStatusRequests === 0) {
        interceptedStatusRequests += 1
        await route.fulfill({
          status: 503,
          contentType: 'application/json',
          headers: { 'X-Request-ID': `${RUN_ID}-csv-status-interrupted` },
          body: JSON.stringify({
            code: 'QA_STATUS_INTERRUPTED',
            message: 'QA injected one persisted-status read failure.',
            details: null,
            request_id: `${RUN_ID}-csv-status-interrupted`,
          }),
        })
        return
      }
      await route.continue()
    })
    const csvUsername = `qa_csv_browser_${suffix}`
    const csv = [
      'username,display_name,initial_password,department,learning_group',
      `${csvUsername},A30 Browser CSV,,QA,BrowserBatch`,
    ].join('\n')
    await page.locator('input[type="file"]').setInputFiles({
      name: 'a30-browser.csv',
      mimeType: 'text/csv',
      buffer: Buffer.from(csv, 'utf8'),
    })
    const previewResponsePromise = page.waitForResponse(
      (response) => response.request().method() === 'POST' && response.url().endsWith('/api/v1/admin/users/import/preview'),
      { timeout: PHASE_TIMEOUT_MS },
    )
    await page.getByRole('button', { name: '上传并预览', exact: true }).click()
    const previewResponse = await previewResponsePromise
    evidence.check('CSV preview succeeds through the browser', previewResponse.status() === 200)
    await page.getByText('可导入', { exact: true }).first().waitFor()
    await evidence.screenshot(page, '11-csv-preview')

    const confirmResponsePromise = page.waitForResponse(
      (response) => response.request().method() === 'POST' && response.url().endsWith('/api/v1/admin/users/import'),
      { timeout: PHASE_TIMEOUT_MS },
    )
    await page.getByRole('button', { name: /确认导入 1 行/ }).click()
    const confirmResponse = await confirmResponsePromise
    evidence.check('CSV import confirms as one atomic batch', confirmResponse.status() === 202)
    const csvDialog = page.getByRole('dialog', { name: '一次性临时密码' })
    await csvDialog.waitFor()
    const csvTemporaryPassword = (await csvDialog.locator('.secret-value code').first().innerText()).trim()
    evidence.check('CSV generated password is shown once', csvTemporaryPassword.length >= 12)
    await evidence.screenshot(page, '12-csv-import-one-time-password', [csvDialog.locator('.secret-value')])
    await csvDialog.getByRole('button', { name: '我已安全保存，关闭' }).click()
    await page.getByText('CSV 批次已导入').waitFor()
    await page.waitForTimeout(300)
    evidence.check('CSV status read is interrupted once for retry coverage', interceptedStatusRequests === 1, {
      intercepted_status_requests: interceptedStatusRequests,
    })
    await evidence.screenshot(page, '13-csv-status-read-interrupted')

    const retryResponsePromise = page.waitForResponse(
      (response) => response.request().method() === 'GET' && /\/api\/v1\/admin\/users\/import\/[^/]+$/.test(new URL(response.url()).pathname),
      { timeout: PHASE_TIMEOUT_MS },
    )
    await page.getByRole('button', { name: '重新读取批次状态', exact: true }).click()
    const retryResponse = await retryResponsePromise
    evidence.check('CSV status retry uses the confirmed import id', retryResponse.status() === 200, {
      status: retryResponse.status(),
      request_id: retryResponse.headers()['x-request-id'] || null,
    })
    await page.getByText('服务端状态：').waitFor()
    await page.getByText('已导入', { exact: true }).last().waitFor()
    await evidence.screenshot(page, '14-csv-status-retried')
    await page.unroute('**/api/v1/admin/users/import/*')

    const logoutResponsePromise = page.waitForResponse(isLogout, { timeout: PHASE_TIMEOUT_MS })
    await page.getByRole('button', { name: '退出登录', exact: true }).click()
    const loggedOut = await logoutResponsePromise
    evidence.check('logout reaches the real API', loggedOut.status() === 204, {
      status: loggedOut.status(),
      request_id: loggedOut.headers()['x-request-id'] || null,
    })
    await page.waitForURL('**/login', { timeout: PHASE_TIMEOUT_MS })
    const remainingCookies = await adminContext.cookies()
    evidence.check(
      'logout clears refresh and CSRF cookies',
      !remainingCookies.some((cookie) => cookie.name === 'refresh_token' || cookie.name === 'csrf_token'),
      { remaining_cookie_names: remainingCookies.map((cookie) => cookie.name).sort() },
    )
    await evidence.screenshot(page, '15-logged-out')

    await page.waitForTimeout(300)
    const allNetworkSensitiveHits = evidence.network.flatMap((entry) => entry.body?.sensitive_key_hits || [])
    evidence.check('browser-observed admin APIs expose no private learning fields', allNetworkSensitiveHits.length === 0, {
      hits: [...new Set(allNetworkSensitiveHits)],
    })
    evidence.check('no uncaught browser page errors occurred', pageErrors.length === 0, {
      page_error_count: pageErrors.length,
      page_errors: pageErrors,
    })

    const apiRequests = evidence.network.length
    const requestIds = evidence.network.map((entry) => entry.request_id).filter(Boolean)
    evidence.check('browser evidence contains correlated request ids', requestIds.length >= 10, {
      api_request_count: apiRequests,
      request_id_count: requestIds.length,
    })

    await memberContext.close()
    await adminContext.close()
  } finally {
    await browser.close()
  }
}

let failure = null
try {
  await main()
} catch (error) {
  failure = `${error?.name || 'Error'}: ${error?.message || String(error)}`
  console.error(failure)
}

await new Promise((resolve) => setTimeout(resolve, 250))
const output = evidence.finish(failure)
const outputPath = path.join(EVIDENCE_DIR, 'browser-e2e-result.json')
await writeFile(outputPath, `${JSON.stringify(output, null, 2)}\n`, 'utf8')
console.log(`RESULT=${outputPath}`)
process.exit(failure ? 1 : 0)