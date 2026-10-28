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
    expect(shell).toContain("label: '学习中心'")
    expect(shell).toContain("label: '词书'")
    expect(shell).not.toContain("label: '组织管理'")
    expect(shell).toContain("label: '设置'")
    expect(shell).not.toContain("label: '每日闯关'")
    expect(shell).not.toContain("label: '记忆练习'")
    expect(shell).not.toContain("label: 'AI 练习'")
    expect(shell).toContain('AI 教练')
    expect(shell).not.toContain('通知中心')

    const today = source('../views/TodayView.vue')
    expect(today).toContain('今日学习')
    expect(today).toContain('继续学习')
    expect(today).toContain('今日任务')
    expect(today).toContain('当前词书')

    const wordbooks = source('../views/WordbooksView.vue')
    expect(wordbooks).toContain('个人词书')
    expect(wordbooks).toContain('当前主词书')

    const practice = source('../views/PracticeHubView.vue')
    expect(practice).toContain('AI 练习')
    expect(practice).toContain('生成练习')
    expect(practice).toContain('最近记录')

    const challenge = source('../views/ChallengeView.vue')
    expect(challenge).toContain('每日闯关')
    expect(challenge).toContain('今日主线')

    const coach = source('../views/CoachView.vue')
    expect(coach).toContain('AI 教练')
    expect(coach).toContain('开始对话')

    const settings = source('../views/LearningSettingsView.vue')
    expect(settings).toContain('学习设置')
    expect(settings).toContain('保存设置')

    const aiSettings = source('../views/PersonalAiConfigView.vue')
    expect(aiSettings).toContain('你的 AI 提供商')
    expect(aiSettings).toContain('添加 AI 提供商')
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
