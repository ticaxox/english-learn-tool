/**
 * Sample payloads for the motion lab only.
 *
 * Same shapes the server returns; nothing here is imported by the app.
 */

export const WEEKLY = {
  days: [
    { date: '2026-11-04', xp: 0, crumbs: 0, active: false },
    { date: '2026-11-05', xp: 120, crumbs: 30, active: true },
    { date: '2026-11-06', xp: 260, crumbs: 60, active: true },
    { date: '2026-11-07', xp: 90, crumbs: 20, active: true },
    { date: '2026-11-08', xp: 0, crumbs: 0, active: false },
    { date: '2026-11-09', xp: 340, crumbs: 80, active: true },
    { date: '2026-11-10', xp: 180, crumbs: 40, active: true },
  ],
  xp: 990,
  active_days: 5,
  streak: 5,
  goals: [
    { key: 'days', label: '一周学习 5 天', progress: 5, target: 5, completed: true },
    { key: 'xp', label: '本周累计 800 XP', progress: 990, target: 800, completed: true },
    { key: 'boss', label: '通过一次终点挑战', progress: 0, target: 1, completed: false },
  ],
}

export const BADGES = {
  items: [
    { key: 'first_lesson', name: '初次点灯', description: '完成第一次学习', unlocked: true, unlocked_at: '2026-10-28T09:12:00' },
    { key: 'streak_3', name: '三日不灭', description: '灯连着亮 3 夜', unlocked: true, unlocked_at: '2026-10-31T21:04:00' },
    { key: 'streak_7', name: '七日长明', description: '灯连着亮 7 夜', unlocked: true, unlocked_at: '2026-11-06T20:31:00' },
    { key: 'streak_30', name: '一月不熄', description: '灯连着亮 30 夜', unlocked: false, unlocked_at: null },
    { key: 'level_5', name: '挑灯人', description: '达到 5 级', unlocked: true, unlocked_at: '2026-11-09T19:47:00' },
    { key: 'level_10', name: '守灯人', description: '达到 10 级', unlocked: false, unlocked_at: null },
    { key: 'practice_10', name: '练习成瘾', description: '累计提交 10 组练习', unlocked: true, unlocked_at: '2026-11-07T18:20:00' },
    { key: 'practice_50', name: '题海老手', description: '累计提交 50 组练习', unlocked: false, unlocked_at: null },
    { key: 'perfect_5', name: '灯下无暗', description: '五组练习全部答对', unlocked: false, unlocked_at: null },
    { key: 'boss_1', name: '首破夜关', description: '首次通过闯关终点', unlocked: false, unlocked_at: null },
    { key: 'review_100', name: '百词成诵', description: '累计复习 100 张卡片', unlocked: true, unlocked_at: '2026-11-08T10:05:00' },
    { key: 'quest_all', name: '一夜三添', description: '一天内完成三条每日任务', unlocked: false, unlocked_at: null },
    { key: 'streak_14', name: '半月不熄', description: '灯连着亮 14 夜', unlocked: true, unlocked_at: '2026-10-30T08:10:00' },
    { key: 'streak_100', name: '百日长明', description: '灯连着亮 100 夜', unlocked: false, unlocked_at: null },
    { key: 'level_3', name: '初添灯油', description: '达到 3 级', unlocked: true, unlocked_at: '2026-10-25T12:00:00' },
    { key: 'level_20', name: '照夜人', description: '达到 20 级', unlocked: false, unlocked_at: null },
    { key: 'practice_100', name: '百炼成钢', description: '累计提交 100 组练习', unlocked: true, unlocked_at: '2026-11-05T19:30:00' },
    { key: 'perfect_20', name: '二十夜无暗', description: '二十组练习全部答对', unlocked: false, unlocked_at: null },
    { key: 'boss_10', name: '十度夜行', description: '通过十次闯关终点', unlocked: false, unlocked_at: null },
    { key: 'review_1000', name: '千词之海', description: '累计复习 1000 张卡片', unlocked: true, unlocked_at: '2026-11-02T07:45:00' },
    { key: 'first_boss_win', name: '破晓者', description: '首次击败终点守卫', unlocked: true, unlocked_at: '2026-10-24T21:15:00' },
    { key: 'night_owl', name: '夜猫子', description: '在深夜完成一次学习', unlocked: false, unlocked_at: null },
    { key: 'early_bird', name: '早起的鸟', description: '在清晨完成一次学习', unlocked: true, unlocked_at: '2026-11-09T06:20:00' },
  ],
}

const NODES = [
  { id: 'review-1', title: '复习回廊', type: '复习', question: '翻卡记忆', minutes: 8, description: '复习到期单词。', previous: '开始' },
  { id: 'new-1', title: '新词营地', type: '学习新词', question: '翻卡记忆', minutes: 5, description: '学习今天的新词。', previous: 'review-1' },
  { id: 'drill-1', title: '拼写矿坑', type: '拼写', question: '拼写', minutes: 6, description: '把新词拼一遍。', previous: 'new-1' },
  { id: 'choice-1', title: '选择题市集', type: '练习', question: '选择', minutes: 5, description: '在句子里认出它们。', previous: 'drill-1' },
  { id: 'boss-1', title: '终点挑战', type: '终点挑战', question: '填空', minutes: 4, description: '用填空收尾。', previous: 'choice-1' },
]

/** `done` = how many main stops are already cleared. */
export function mapDsl(done: number): string {
  const status = (index: number): string => {
    if (index < done) return '已完成'
    if (index === done) return '进行中'
    if (index === done + 1) return '已解锁'
    return '未解锁'
  }
  const lines: string[] = ['# 今日闯关', '> 先复习，再学习。', '']
  NODES.forEach((node, index) => {
    lines.push(
      `## [${node.id}] ${node.title}`,
      `- 类型: ${node.type}`,
      `- 题目类型: ${node.question}`,
      `- 状态: ${status(index)}`,
      `- 时长: ${node.minutes} 分钟`,
      `- 说明: ${node.description}`,
      `- 链接: /memory`,
      `- 前置: ${node.previous}`,
      `- 可选: 否`,
      '',
    )
  })
  lines.push(
    '## [side-1] 侧巷小测',
    '- 类型: 支线',
    '- 题目类型: 选择',
    '- 状态: 已解锁',
    '- 时长: 3 分钟',
    '- 说明: 可选加练。',
    '- 链接: /memory',
    '- 前置: new-1',
    '- 可选: 是',
    '',
  )
  return lines.join('\n')
}

/** One shelf of books, and the entries behind the first one. */
export const SHELF = [
  { id: '1', name: '四级核心词汇', description: '按真题频率排序', entry_count: 1200, version: '3', visibility: 'organization', status: 'ready', is_active: true, created_at: '2026-11-01T10:00:00', updated_at: '2026-11-09T10:00:00' },
  { id: '2', name: '考研阅读高频', description: '十年真题里反复出现的词', entry_count: 860, version: '2', visibility: 'organization', status: 'ready', is_active: false, created_at: '2026-11-02T10:00:00', updated_at: '2026-11-08T10:00:00' },
  { id: '3', name: '我的错词本', description: '', entry_count: 86, version: '1', visibility: 'private', status: 'ready', is_active: false, created_at: '2026-11-03T10:00:00', updated_at: '2026-11-08T10:00:00' },
  { id: '4', name: '六级听力场景词', description: '校园、租房、面试三组场景', entry_count: 430, version: '1', visibility: 'organization', status: 'ready', is_active: false, created_at: '2026-11-04T10:00:00', updated_at: '2026-11-07T10:00:00' },
  { id: '5', name: '雅思写作替换词', description: '', entry_count: 152, version: '1', visibility: 'private', status: 'ready', is_active: false, created_at: '2026-11-05T10:00:00', updated_at: '2026-11-06T10:00:00' },
  { id: '6', name: '商务英语 800', description: '邮件与会议场景', entry_count: 800, version: '4', visibility: 'organization', status: 'ready', is_active: false, created_at: '2026-11-06T10:00:00', updated_at: '2026-11-09T10:00:00' },
] as never[]

const WORDS: Array<[string, string, string, string]> = [
  ['harbor', '/ˈhɑːbə/', 'v.', '怀有（想法、感情）'],
  ['commute', '/kəˈmjuːt/', 'v.', '通勤'],
  ['landmark', '/ˈlændmɑːk/', 'n.', '地标；里程碑'],
  ['subsidy', '/ˈsʌbsədi/', 'n.', '补贴，津贴'],
  ['thrive', '/θraɪv/', 'v.', '兴旺，茁壮成长'],
  ['sustainable', '/səˈsteɪnəbl/', 'adj.', '可持续的'],
]

export const BOOK_ENTRIES = WORDS.map(([headword, phonetic, pos, zh], index) => ({
  id: `entry-${index + 1}`,
  headword,
  normalized_headword: headword.toLowerCase(),
  phonetic,
  definitions: [{ part_of_speech: pos, definition_en: null, definition_zh: zh, examples: [] }],
}))

/** The wordbook detail payload the API would return for one book. */
export function bookDetail(id: string): unknown {
  const book = (SHELF as Array<{ id: string }>).find((item) => item.id === id) ?? (SHELF as Array<{ id: string }>)[0]
  return {
    wordbook: book,
    entries: BOOK_ENTRIES,
    total_entries: BOOK_ENTRIES.length,
    offset: 0,
    limit: 50,
  }
}

/** One choice question and one spelling question, for the drill surfaces. */
export const CHOICE_QUESTION = {
  kind: 'choice',
  questionId: 'choice-demo',
  prompt: 'harbor',
  phonetic: '/ˈhɑːbə/',
  partOfSpeech: 'v.',
  optionCount: 4,
  remaining: 12,
  options: [
    { optionId: 'a', label: '港口' },
    { optionId: 'b', label: '怀有（想法、感情）' },
    { optionId: 'c', label: '藏匿' },
    { optionId: 'd', label: '停泊' },
  ],
} as never

export const SPELLING_QUESTION = {
  kind: 'spelling',
  questionId: 'spelling-demo',
  definition: '怀有（想法、感情）',
  phonetic: '/ˈhɑːbə/',
  partOfSpeech: 'v.',
  blankType: null,
  cloze: 'She harbor s a deep love for the city.',
  remaining: 8,
  blanks: [{ index: 4, prefilled: false, character: null }],
} as never


/** The player bar's payload: level, streak, crumbs and today's quests. */
export const PROGRESS = {
  xp: 1480,
  crumbs: 260,
  level: { level: 6, title: '挑灯人', xp_into_level: 180, xp_for_next_level: 460 },
  streak: 9,
  streak_best: 12,
  active_today: true,
  freeze_tokens: 1,
  local_date: '2026-11-11',
  quests: [
    { key: 'review_due', progress: 14, target: 20, completed: false, reward_crumbs: 30 },
    { key: 'practice_one', progress: 1, target: 1, completed: true, reward_crumbs: 40 },
    { key: 'challenge_done', progress: 0, target: 1, completed: false, reward_crumbs: 60 },
  ],
}
