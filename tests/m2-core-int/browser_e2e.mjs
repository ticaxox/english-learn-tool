#!/usr/bin/env node
/**
 * M2-CORE-INT-001 Phase A browser acceptance runner.
 *
 * Drives the real production bundle (nginx-served Vue SPA behind the nginx
 * reverse proxy, talking to the containerized API) through a real Chromium
 * engine. It closes the three gaps A20 left open: real file uploads for
 * CSV/JSON/TXT, a real delete-confirmation click, and a member activation
 * screenshot. Every step records a screenshot and a structured result.
 *
 * Engine note: no Google Chrome build is installed on this host, so the runner
 * uses the installed Microsoft Edge binary through playwright-core instead of
 * silently skipping UI coverage.
 */
import { mkdirSync, writeFileSync, readFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const BASE_URL = process.env.LIVE_WEB_BASE_URL || 'http://127.0.0.1:8091'
const RUN_ID = process.env.LIVE_RUN_ID || 'phase-a-browser-run1'
const EVIDENCE_DIR = process.env.EVIDENCE_DIR
const RUNTIME_ENV = process.env.RUNTIME_ENV
const EDGE =
  process.env.LIVE_BROWSER_EXECUTABLE ||
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'

if (!EVIDENCE_DIR) {
  console.error('EVIDENCE_DIR is required')
  process.exit(2)
}

/**
 * playwright-core is resolved from an explicit module path instead of a local
 * node_modules tree, because this test asset lives in the repository while the
 * disposable browser harness lives in the agent session temp directory.
 */
const PLAYWRIGHT_MODULE =
  process.env.LIVE_PLAYWRIGHT_MODULE ||
  'E:\\agent workspace\\英语学习工具\\ai-workspace\\10-collaboration\\sessions\\A20-VIEW\\temp\\a20-browser-check\\node_modules\\playwright-core\\index.mjs'

const { chromium } = await import(pathToFileURL(PLAYWRIGHT_MODULE).href)

const RUN_DIR = join(EVIDENCE_DIR, 'results', RUN_ID)
const SHOT_DIR = join(RUN_DIR, 'screenshots')
mkdirSync(SHOT_DIR, { recursive: true })

function readRuntimeEnv() {
  const values = {}
  if (!RUNTIME_ENV) return values
  for (const line of readFileSync(RUNTIME_ENV, 'utf8').split(/\r?\n/)) {
    const match = line.match(/^([A-Z0-9_]+)=(.*)$/)
    if (match) values[match[1]] = match[2]
  }
  return values
}

const RUNTIME = readRuntimeEnv()
const ADMIN_PASSWORD = RUNTIME.QA_BOOTSTRAP_ADMIN_PASSWORD
// Synthetic fixture credential for the disposable local QA member account only.
const MEMBER_PASSWORD = process.env.LIVE_MEMBER_PASSWORD || 'Qa-M2Core-Member-2026!x'
const STAMP = new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14)

const checks = []
const artifacts = {}
const consoleMessages = []
const failedRequests = []
const httpErrors = []

class CheckFailure extends Error {}

function pass(name, details = {}) {
  checks.push({ name, status: 'PASS', details })
  console.log(`[PASS] ${name}`)
}

function fail(name, details = {}) {
  checks.push({ name, status: 'FAIL', details })
  console.log(`[FAIL] ${name} ${JSON.stringify(details).slice(0, 600)}`)
  throw new CheckFailure(name)
}

function assert(name, condition, details = {}) {
  if (condition) pass(name, details)
  else fail(name, details)
  return condition
}

/**
 * Signs in through the real login form. The account may need its first-login
 * password rotation, and a rerun against a warm database finds the rotated
 * password already active, so both candidates are tried before failing.
 */
async function signIn(page, username, passwords) {
  for (const password of passwords) {
    await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' })
    await page.evaluate(() => window.localStorage.clear())
    await page.fill('#username', username)
    await page.fill('#password', password)
    await page.click('button[type=submit]')
    try {
      await page.waitForURL(/\/(change-password|overview|wordbooks)/, { timeout: 15000 })
      return password
    } catch {
      /* try the next candidate */
    }
  }
  throw new CheckFailure(`sign-in failed for ${username}`)
}

/** Completes the forced first-login password change if the SPA routed there. */
async function completeForcedPasswordChange(page, username, oldPassword, newPassword) {
  if (!page.url().includes('change-password')) {
    return { rotated: false }
  }
  await shot(page, `change-password-${username}`)
  await page.fill('#old-password', oldPassword)
  await page.fill('#new-password', newPassword)
  await page.fill('#confirm-password', newPassword)
  await page.click('button[type=submit]')
  await page.waitForURL(/\/(login|overview|wordbooks)/, { timeout: 25000 })
  if (page.url().includes('/login')) {
    await page.fill('#username', username)
    await page.fill('#password', newPassword)
    await page.click('button[type=submit]')
    await page.waitForURL(/\/(overview|wordbooks)/, { timeout: 20000 })
  }
  return { rotated: true }
}

/**
 * Clicks a real <button> by its exact visible label. Plain text locators also
 * match status paragraphs and aria-labels, which sit behind the modal backdrop
 * and therefore cannot receive the click.
 */
async function clickButton(page, label) {
  const button = page.getByRole('button', { name: label, exact: true })
  await button.waitFor({ state: 'visible', timeout: 30000 })
  await button.click()
  return button
}

/**
 * The delete dialog unmounts itself as soon as the parent view receives the
 * `completed` event (WordbooksView.deletionCompleted clears deleteTarget), so
 * the "完成" button can be gone by the time Playwright looks for it. Closing is
 * therefore best-effort and never the pass criterion.
 */
async function closeDialogIfPresent(page) {
  const dialogs = page.locator('[role=dialog]')
  if ((await dialogs.count()) === 0) {
    return { alreadyClosed: true, method: 'auto-unmounted' }
  }
  const done = page.getByRole('button', { name: '完成', exact: true })
  let method = 'escape'
  if ((await done.count()) > 0) {
    method = 'completion-button'
    await done.last().click().catch(() => {})
  } else {
    await page.keyboard.press('Escape').catch(() => {})
  }
  await dialogs.first().waitFor({ state: 'detached', timeout: 15000 }).catch(() => {})
  return { alreadyClosed: (await dialogs.count()) === 0, method }
}

async function shot(page, name, options = {}) {
  const file = join(SHOT_DIR, `${name}.png`)
  await page.screenshot({ path: file, fullPage: options.fullPage !== false })
  artifacts[name] = file
  return file
}

function mimeFor(name) {
  if (name.endsWith('.json')) return 'application/json'
  if (name.endsWith('.txt')) return 'text/plain'
  return 'text/csv'
}

async function attachFile(page, name, buffer) {
  await page.setInputFiles('input[type=file]', { name, mimeType: mimeFor(name), buffer })
}

/** CSV fixture with an extra unmapped column to exercise the mapping panel. */
const CSV_FIXTURE = Buffer.from(
  'headword,phonetic,part_of_speech,definition_en,definition_zh,example,example_translation,source\n' +
    'abandon,/\u0259\u02c8b\u00e6nd\u0259n/,verb,to leave behind,\u653e\u5f03,' +
    'He abandoned the plan.,\u4ed6\u653e\u5f03\u4e86\u8ba1\u5212\u3002,web\n' +
    'brief,/bri\u02d0f/,adj,lasting a short time,\u77ed\u6682\u7684,' +
    'A brief pause.,\u77ed\u6682\u7684\u505c\u987f\u3002,web\n',
  'utf8',
)

/** Flat JSON rows: the importer maps keys through the same table as CSV. */
const JSON_FIXTURE = Buffer.from(
  JSON.stringify(
    [
      {
        headword: 'diligent',
        phonetic: '/\u02c8d\u026al\u026ad\u0292\u0259nt/',
        part_of_speech: 'adj',
        definition_en: 'showing careful and persistent effort',
        definition_zh: '\u52e4\u594b\u7684',
        example: 'A diligent student.',
        example_translation: '\u4e00\u4e2a\u52e4\u594b\u7684\u5b66\u751f\u3002',
      },
      {
        headword: 'eager',
        phonetic: '/\u02c8i\u02d0\u0261\u0259/',
        part_of_speech: 'adj',
        definition_en: 'wanting to do something very much',
        definition_zh: '\u70ed\u5207\u7684',
        example: 'Eager to learn.',
        example_translation: '\u6e34\u671b\u5b66\u4e60\u3002',
      },
    ],
    null,
    2,
  ),
  'utf8',
)

/**
 * GB18030-encoded TXT: a real non-UTF-8 upload. TXT wordbooks are headerless
 * tab-separated rows in canonical field order, so the encoding probe must
 * succeed on real GB18030 Chinese bytes rather than on a UTF-8 stand-in.
 *
 * The bytes below were produced once with Python's gb18030 codec for exactly
 * these lines and verified to contain non-ASCII bytes that are invalid UTF-8,
 * so this fixture exercises the server-side decode path instead of relying on
 * a re-encoding step inside the test process.
 */
const TXT_FIXTURE = Buffer.from(
  'ZnJ1Z2FsCS+BMLc0ZnJ1gTC3OajAgTCsNWwvCWFkagljYXJlZnVsIHdpdGggbW9uZXkJvdq887XECUEgZnJ1Z2Fs' +
    'IGhvdXNlaG9sZC4J0ru49r3avPO1xLzSzaWhowpncmFzcAkvqMByqLuBMLc5c3AvCXZlcmIJdG8gdW5kZXJz' +
    'dGFuZCBmdWxseQnB7LvhCUkgZ3Jhc3BlZCB0aGUgaWRlYS4JztLB7LvhwcvV4rj2z+u3qKGjCg==',
  'base64',
)
async function main() {
  const browser = await chromium.launch({
    executablePath: EDGE,
    headless: true,
    args: ['--disable-dev-shm-usage', '--no-sandbox'],
  })
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    acceptDownloads: true,
  })
  const page = await context.newPage()
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleMessages.push({
        text: message.text().slice(0, 300),
        url: message.location()?.url ?? '',
      })
    }
  })
  page.on('requestfailed', (request) => {
    failedRequests.push(`${request.method()} ${new URL(request.url()).pathname}`)
  })
  // Record every HTTP error status with its verb/path so auth-boundary 401s the
  // harness itself provokes (cookie clearing, logout, refresh) stay auditable
  // instead of being swallowed by a blanket filter.
  page.on('response', (response) => {
    if (response.status() >= 400) {
      httpErrors.push({
        status: response.status(),
        request: `${response.request().method()} ${new URL(response.url()).pathname}`,
        at: new Date().toISOString(),
      })
    }
  })

  let status = 'PASS'
  let error = null
  try {
    // ---- 1. Load the SPA from the real nginx edge -----------------------
    const response = await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' })
    assert('web.spa.served-by-nginx-edge', response.status() === 200, {
      status: response.status(),
      url: page.url(),
      server: response.headers()['server'] || 'hidden',
    })
    await page.waitForSelector('#username')
    await shot(page, '01-login-page')

    // ---- 2-3. Real browser login as the administrator -------------------
    // The database may be warm: an earlier API acceptance run can already have
    // rotated the first-login password, so both candidates are tried in order.
    const usedAdminPassword = await signIn(page, 'qa_m2core_admin', [
      ADMIN_PASSWORD,
      `${ADMIN_PASSWORD}.Rotated1`,
    ])
    let activeAdminPassword = usedAdminPassword
    assert('web.admin.login.navigates-into-app', !page.url().includes('/login'), {
      url: page.url(),
    })
    const adminRotation = await completeForcedPasswordChange(
      page,
      'qa_m2core_admin',
      usedAdminPassword,
      `${ADMIN_PASSWORD}.Rotated1`,
    )
    if (adminRotation.rotated) {
      activeAdminPassword = `${ADMIN_PASSWORD}.Rotated1`
      pass('web.admin.password-rotation.through-ui')
    } else {
      pass('web.admin.password-rotation.already-completed', {
        note: 'warm database: forced rotation was completed by an earlier run',
        usedOriginalPassword: usedAdminPassword === ADMIN_PASSWORD,
      })
    }

    // ---- 4. Wordbooks page ---------------------------------------------
    await page.goto(`${BASE_URL}/wordbooks`, { waitUntil: 'networkidle' })
    await page.waitForSelector('text=＋ 导入词书', { timeout: 20000 })
    await shot(page, '04-wordbooks-page-admin')
    pass('web.wordbooks.page.loads-real-data')

    // ---- 5. REAL CSV upload through the file input ---------------------
    const csvName = `QA Phase A Web CSV ${STAMP}`
    await clickButton(page, '＋ 导入词书')
    await page.waitForSelector('text=导入真实词书')
    await page.selectOption('select', 'organization')
    await page.fill('input[type=text]', csvName)
    await attachFile(page, 'qa-web-csv.csv', CSV_FIXTURE)
    await shot(page, '05-csv-file-selected')
    pass('web.import.csv.real-file-attached', { filename: 'qa-web-csv.csv' })

    await clickButton(page, '预览并检查映射')
    await page.waitForSelector('text=服务端结构化样例', { timeout: 25000 })
    await shot(page, '06-csv-preview-mapping')
    pass('web.import.csv.preview-renders-mapping')

    await clickButton(page, '确认导入')
    await page.waitForSelector('text=导入已完成', { timeout: 90000 })
    await shot(page, '07-csv-import-completed')
    pass('web.import.csv.confirm-completes')
    await clickButton(page, '完成')
    await page.waitForTimeout(2500)
    await page.reload({ waitUntil: 'networkidle' })
    await page.waitForSelector(`text=${csvName}`, { timeout: 25000 })
    await shot(page, '08-csv-card-visible')
    pass('web.import.csv.card-appears-in-list', { name: csvName })

    // ---- 6. Detail dialog ---------------------------------------------
    await page.click(`[aria-label="查看 ${csvName} 的词条"]`)
    await page.waitForSelector('text=abandon', { timeout: 20000 })
    await shot(page, '09-organization-detail-dialog')
    pass('web.wordbook.detail.shows-entries')
    await page.keyboard.press('Escape')
    await page.waitForTimeout(600)

    // ---- 7. REAL export + real download through the UI -----------------
    await page.click(`[aria-label="导出 ${csvName}"]`)
    await page.waitForSelector('text=开始导出', { timeout: 15000 })
    await shot(page, '10-export-dialog')
    await clickButton(page, '开始导出')
    const downloadSelector = 'button:has-text("下载 ")'
    await page.waitForSelector(downloadSelector, { timeout: 90000 })
    await shot(page, '10b-export-ready')
    const downloadPromise = page.waitForEvent('download', { timeout: 60000 })
    await page.locator(downloadSelector).first().click()
    const download = await downloadPromise
    const savedPath = join(RUN_DIR, 'downloads')
    mkdirSync(savedPath, { recursive: true })
    const target = join(savedPath, download.suggestedFilename())
    await download.saveAs(target)
    artifacts.exportDownload = target
    await shot(page, '11-export-downloaded')
    assert('web.export.real-download.completes', readFileSync(target).length > 0, {
      filename: download.suggestedFilename(),
      bytes: readFileSync(target).length,
    })
    await clickButton(page, '完成').catch(() => page.keyboard.press('Escape'))
    await page.waitForTimeout(800)

    // ---- 8. REAL delete confirmation click -----------------------------
    await page.reload({ waitUntil: 'networkidle' })
    await page.waitForSelector(`text=${csvName}`, { timeout: 25000 })
    await page.click(`[aria-label="删除 ${csvName}"]`)
    await page.waitForSelector(`text=删除「${csvName}」`, { timeout: 15000 })
    await shot(page, '12-delete-dialog-open')
    const deleteDialog = page.locator('[role=dialog]').last()
    const confirmInput = deleteDialog.locator('input[placeholder]').first()
    await confirmInput.fill(csvName)
    await confirmInput.dispatchEvent('input')
    await page.waitForTimeout(300)
    await shot(page, '13-delete-confirmation-typed')
    await clickButton(page, '确认启动删除')
    await page.waitForSelector('text=清理已完成', { timeout: 90000 })
    await shot(page, '14-delete-completed')
    const csvDialogClose = await closeDialogIfPresent(page)
    assert('web.delete.dialog-closes-after-cleanup', csvDialogClose.alreadyClosed, csvDialogClose)
    pass('web.delete.confirmation-click.cleans-up', csvDialogClose)
    await page.waitForTimeout(2000)
    await page.reload({ waitUntil: 'networkidle' })
    await page.waitForTimeout(1500)
    const csvGone = (await page.locator(`text=${csvName}`).count()) === 0
    await shot(page, '15-after-delete-list')
    assert('web.delete.card-removed-after-cleanup', csvGone, { stillVisible: !csvGone })

    // ---- 9. Log out, then real member JSON + GB18030 TXT uploads -------
    await context.clearCookies()
    const usedMemberPassword = await signIn(page, 'qa_m2core_member', [
      MEMBER_PASSWORD,
      `${MEMBER_PASSWORD}.Rotated1`,
    ])
    assert('web.member.login.navigates-into-app', !page.url().includes('/login'), {
      url: page.url(),
    })
    const memberRotation = await completeForcedPasswordChange(
      page,
      'qa_m2core_member',
      usedMemberPassword,
      `${MEMBER_PASSWORD}.Rotated1`,
    )
    if (memberRotation.rotated) {
      pass('web.member.password-rotation.through-ui')
    } else {
      pass('web.member.password-rotation.already-completed', {
        note: 'warm database: forced rotation was completed by an earlier run',
        usedOriginalPassword: usedMemberPassword === MEMBER_PASSWORD,
      })
    }

    await page.goto(`${BASE_URL}/wordbooks`, { waitUntil: 'networkidle' })
    await page.waitForSelector('text=＋ 导入词书', { timeout: 20000 })
    await shot(page, '16-wordbooks-page-member')

    const jsonName = `QA Phase A Web JSON ${STAMP}`
    await clickButton(page, '＋ 导入词书')
    await page.waitForSelector('text=导入真实词书')
    await page.fill('input[type=text]', jsonName)
    await attachFile(page, 'qa-web-member.json', JSON_FIXTURE)
    await shot(page, '17-json-file-selected')
    pass('web.import.json.real-file-attached', { filename: 'qa-web-member.json' })
    await clickButton(page, '预览并检查映射')
    await page.waitForSelector('text=服务端结构化样例', { timeout: 25000 })
    await shot(page, '18-json-preview')
    await clickButton(page, '确认导入')
    await page.waitForSelector('text=导入已完成', { timeout: 90000 })
    await shot(page, '19-json-import-completed')
    pass('web.import.json.confirm-completes')
    await clickButton(page, '完成')
    await page.waitForTimeout(2000)
    await page.reload({ waitUntil: 'networkidle' })
    await page.waitForSelector(`text=${jsonName}`, { timeout: 25000 })
    pass('web.import.json.private-card-visible', { name: jsonName })

    const txtName = `QA Phase A Web TXT ${STAMP}`
    await clickButton(page, '＋ 导入词书')
    await page.waitForSelector('text=导入真实词书')
    await page.fill('input[type=text]', txtName)
    await attachFile(page, 'qa-web-member.txt', TXT_FIXTURE)
    await shot(page, '20-txt-file-selected')
    pass('web.import.txt.real-file-attached', { filename: 'qa-web-member.txt' })
    await clickButton(page, '预览并检查映射')
    await page.waitForSelector('text=服务端结构化样例', { timeout: 25000 })
    await shot(page, '21-txt-preview-gb18030')
    await clickButton(page, '确认导入')
    await page.waitForSelector('text=导入已完成', { timeout: 90000 })
    await shot(page, '22-txt-import-completed')
    pass('web.import.txt.gb18030-confirm-completes')
    await clickButton(page, '完成')
    await page.waitForTimeout(2000)
    await page.reload({ waitUntil: 'networkidle' })
    await page.waitForSelector(`text=${txtName}`, { timeout: 25000 })
    pass('web.import.txt.private-card-visible', { name: txtName })

    // ---- 10. Member activation screenshot ------------------------------
    await page.click(`[aria-label="将 ${txtName} 设为当前主词书"]`)
    await page.waitForSelector('text=当前主词书', { timeout: 30000 })
    await shot(page, '23-member-activation-success')
    pass('web.member.activation.shows-primary-badge', { wordbook: txtName })

    // ---- 11. Member private detail stays private -----------------------
    await page.click(`[aria-label="查看 ${txtName} 的词条"]`)
    await page.waitForSelector('text=frugal', { timeout: 20000 })
    await shot(page, '24-member-private-detail')
    pass('web.member.private-detail.visible-to-owner')
    await page.keyboard.press('Escape')
    await page.waitForTimeout(800)

    // ---- 12. Real private delete confirmation --------------------------
    await page.click(`[aria-label="删除 ${jsonName}"]`)
    await page.waitForSelector(`text=删除「${jsonName}」`, { timeout: 15000 })
    await page.locator('input[type=checkbox]').check()
    await shot(page, '25-private-delete-checkbox')
    await clickButton(page, '确认启动删除')
    await page.waitForSelector('text=清理已完成', { timeout: 90000 })
    await shot(page, '26-private-delete-completed')
    const privateDialogClose = await closeDialogIfPresent(page)
    assert('web.delete.private-dialog-closes-after-cleanup', privateDialogClose.alreadyClosed, privateDialogClose)
    pass('web.delete.private-checkbox-confirmation.cleans-up', privateDialogClose)
    await page.waitForTimeout(1500)

    // ---- 13. Administrator cannot read the member's private wordbook ---
    await context.clearCookies()
    await signIn(page, 'qa_m2core_admin', [
      activeAdminPassword,
      ADMIN_PASSWORD,
      `${ADMIN_PASSWORD}.Rotated1`,
    ])

    await page.goto(`${BASE_URL}/wordbooks`, { waitUntil: 'networkidle' })
    await page.waitForSelector('text=＋ 导入词书', { timeout: 20000 })
    await page.waitForTimeout(1500)
    const adminSeesPrivate = (await page.locator(`text=${txtName}`).count()) > 0
    await shot(page, '27-admin-cannot-see-member-private', { fullPage: true })
    assert('web.private.admin-cannot-see-member-wordbook', !adminSeesPrivate, {
      administratorSawPrivateBook: adminSeesPrivate,
    })
    pass('web.private.admin-list-isolation')

    // Two error classes are expected and are labelled instead of filtered away:
    //  1. Auth-boundary 401s: the harness clears cookies between roles, /login
    //     performs a real /auth/refresh, and sign-in tries the pre-rotation
    //     password first on a warm database.
    //  2. Pre-existing frontend scaffold 404s: the frozen frontend router still
    //     points the placeholder overview page at /learning/today, which does not
    //     exist in the frozen backend OpenAPI (24 paths). This is an inherited
    //     M0/M1 placeholder, not a wordbook regression, and it is recorded as an
    //     explicit coverage note in the Phase A report.
    const AUTH_BOUNDARY = [/\/api\/v1\/auth\/refresh$/, /\/api\/v1\/auth\/login$/]
    const PRE_EXISTING_SCAFFOLD = [/\/api\/v1\/learning\/today$/, /\/api\/v1\/memory\/config$/]
    const classify = (url, status) => {
      if (status === 401 && AUTH_BOUNDARY.some((pattern) => pattern.test(url))) return 'auth-boundary-401'
      if (status === 404 && PRE_EXISTING_SCAFFOLD.some((pattern) => pattern.test(url))) return 'pre-existing-scaffold-404'
      return null
    }
    const consoleStatus = (entry) => {
      const match = /status of (\d+)/.exec(entry.text)
      return match ? Number(match[1]) : null
    }
    const consoleBuckets = { 'auth-boundary-401': 0, 'pre-existing-scaffold-404': 0 }
    const unexpectedConsole = consoleMessages.filter((entry) => {
      const bucket = classify(entry.url, consoleStatus(entry))
      if (bucket) consoleBuckets[bucket] += 1
      return bucket === null
    })
    const httpBuckets = { 'auth-boundary-401': 0, 'pre-existing-scaffold-404': 0 }
    const unexpectedHttp = httpErrors.filter((entry) => {
      const bucket = classify(entry.request.split(' ')[1], entry.status)
      if (bucket) httpBuckets[bucket] += 1
      return bucket === null
    })
    assert('web.console.no-unexpected-errors', unexpectedConsole.length === 0, {
      unexpected: unexpectedConsole.slice(0, 5),
      classifiedExpected: consoleBuckets,
    })
    assert('web.http.no-unexpected-error-status', unexpectedHttp.length === 0, {
      unexpected: unexpectedHttp.slice(0, 8),
      classifiedExpected: httpBuckets,
    })
    assert(
      'web.network.no-failed-requests',
      failedRequests.filter((entry) => !entry.includes('/learning/') && !entry.includes('/memory/'))
        .length === 0,
      { failed: failedRequests.slice(0, 8) },
    )
  } catch (caught) {
    status = 'FAIL'
    error = caught instanceof CheckFailure ? `CheckFailure: ${caught.message}` : String(caught?.stack || caught)
    console.error(error)
    try {
      await shot(page, '99-failure-state')
    } catch {
      /* screenshot of a broken page is best-effort */
    }
  } finally {
    await browser.close()
  }

  const result = {
    task: 'M2-CORE-INT-001',
    phase: 'A',
    run_id: RUN_ID,
    browser: { engine: 'chromium', executable: EDGE, headless: true },
    web_base_url: BASE_URL,
    finished_at: new Date().toISOString(),
    status,
    error,
    checks,
    artifacts,
    console_errors: consoleMessages,
    failed_requests: failedRequests,
    http_errors: httpErrors,
  }
  const out = join(RUN_DIR, 'browser-acceptance.json')
  writeFileSync(out, `${JSON.stringify(result, null, 2)}\n`, 'utf8')
  console.log(`\nRESULT=${status} evidence=${out}`)
  process.exit(status === 'PASS' ? 0 : 1)
}

main().catch((caught) => {
  console.error(caught)
  process.exit(1)
})
