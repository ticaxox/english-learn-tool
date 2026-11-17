import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const memberFiles = [
  '../components/MemberShell.vue',
  '../components/ChoiceTrainer.vue',
  '../components/FlashcardTrainer.vue',
  '../components/PracticeQuestionCard.vue',
  '../components/PracticeResultView.vue',
  '../components/SpellingTrainer.vue',
  '../components/StudyStatsPanel.vue',
  '../components/WordbookShelfCard.vue',
  '../components/WordbookImportDialog.vue',
  '../components/WordbookExportDialog.vue',
  '../components/WordbookDeleteDialog.vue',
  '../views/TodayView.vue',
  '../views/WordbooksView.vue',
  '../views/MemoryPracticeView.vue',
  '../views/PracticeHubView.vue',
  '../views/PracticeSessionView.vue',
  '../views/ChallengeView.vue',
  '../views/CoachView.vue',
  '../views/LearningSettingsView.vue',
  '../views/PersonalAiConfigView.vue',
]

function source(path: string): string {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

describe('merged practice surface', () => {
  it('hosts memory training on the practice page and redirects old links', () => {
    const hub = source('../views/PracticeHubView.vue')
    expect(hub).toContain('MemoryPracticeView')
    expect(hub).toContain('MEMORY_MODULES')
    const routes = source('../router/index.ts')
    expect(routes).toContain("redirect: (to) => ({ name: 'practice', query: to.query })")
  })
})

describe('member-facing Chinese copy density', () => {
  it('does not expose implementation language or editorial placeholder labels', () => {
    const forbidden = [
      '真实 API',
      '真实 SSE',
      '真实 AI',
      '真实学习数据',
      '真实通知',
      '真实词书列表',
      '真实会话',
      '真实消息',
      '真实历史',
      '真实闯关地图',
      '真实通知偏好',
      '服务端',
      '接口契约',
      '状态机',
      'OpenAPI',
      'Request ID',
      'REAL SERVER SNAPSHOT',
      'REAL AI TASKS',
      'REAL SSE',
      'THE DAILY EDITION',
      'THE DAILY TRAIL',
      'THE WORD SHELF',
      'THE PRACTICE ROOM',
      'THE LETTER ROOM',
      'A PRIVATE LETTER ROOM',
      'Moustache Inbox',
      'Moustache Rules',
      'A NOTE FROM THE HAT',
      'Current conversation',
      'Main route',
      'Optional branch',
      'Node detail',
      'No map yet',
      ' words · v',
      'IN USE',
      'ON SHELF',
    ]
    const findings = memberFiles.flatMap((path) => {
      const text = source(path)
      return forbidden
        .filter((phrase) => text.includes(phrase))
        .map((phrase) => path + ": " + phrase)
    })

    expect(findings).toEqual([])
  })

  it('uses concise Chinese labels for the primary member surfaces', () => {
    const shell = source('../components/MemberShell.vue')
    expect(shell).toContain("label: '今日学习'")
    expect(shell).toContain("label: '练习'")
    expect(shell).not.toContain("label: '记忆练习'")
    expect(shell).not.toContain("label: '组织管理'")
    expect(shell).toContain("label: '设置'")
    expect(shell).not.toContain("label: '每日闯关'")
    expect(shell).toContain('Hob')
    expect(shell).not.toContain('通知中心')

    const today = source('../views/TodayView.vue')
    expect(today).toContain('今日学习')
    expect(today).toContain('继续学习')
    expect(today).toContain('今日任务')
    expect(today).toContain('换一本')

    const wordbooks = source('../views/WordbooksView.vue')
    expect(wordbooks).toContain('个人词书')
    expect(wordbooks).toContain('当前主词书')

    const practice = source('../views/PracticeHubView.vue')
    // The practice page hosts both memory training and AI generation.
    expect(practice).toContain('MEMORY_MODULES')
    expect(practice).toContain('生成练习')
    expect(practice).toContain('PracticeTaskList')
    const tasks = source('../components/PracticeTaskList.vue')
    expect(tasks).toContain('题目列表')

    const challenge = source('../views/ChallengeView.vue')
    expect(challenge).toContain('每日闯关')
    expect(challenge).toContain('ChallengeDslMap')

    const coach = source('../views/CoachView.vue')
    expect(coach).toContain('Hob')
    expect(coach).toContain('开始对话')

    const settings = source('../views/LearningSettingsView.vue')
    expect(settings).toContain('学习设置')
    expect(settings).toContain("'保存'")

    const aiSettings = source('../views/PersonalAiConfigView.vue')
    expect(aiSettings).toContain('你的 AI 提供商')
    expect(aiSettings).toContain('对话模型')
    expect(aiSettings).toContain('向量模型')
    expect(aiSettings.match(/>添加<\/DivButton>/g)?.length).toBeGreaterThanOrEqual(1)
  })

  it('keeps long explanatory paragraphs out of the member hero copy', () => {
    const longTechnicalCopy = [
      '今日计划由服务端根据你的学习档案和词书状态生成',
      '这里展示的是当天固定快照',
      '页面不会在本地自行推进复习间隔',
      '不会用静态地图替代真实结果',
      '不使用浏览器业务存储',
      '答案会以服务端草稿恢复',
      '页面会持续读取真实会话状态',
    ]
    const findings = memberFiles.flatMap((path) => {
      const text = source(path)
      return longTechnicalCopy
        .filter((phrase) => text.includes(phrase))
        .map((phrase) => path + ": " + phrase)
    })

    expect(findings).toEqual([])
  })
})
