import { describe, expect, it } from 'vitest'
import { parseChallengeMapDsl } from '../utils/challenge-map'

const DSL = `# 今日闯关
> 先复习，再学习。

## [review-1] 复习回廊
- 类型: 复习
- 题目类型: 翻卡记忆
- 状态: 已解锁
- 时长: 8 分钟
- 说明: 复习到期单词。
- 链接: /memory?module=flashcard
- 前置: 开始
- 分支: new-1
- 可选: 否

## [new-1] 新词营地
- 类型: 学习新词
- 题目类型: 翻卡记忆
- 状态: 未解锁
- 时长: 5 分钟
- 说明: 学习今天的新词。
- 链接: 待开始
- 前置: review-1
- 分支: boss-1
- 可选: 否

## [boss-1] 终点挑战
- 类型: 终点挑战
- 题目类型: 填空
- 状态: 未解锁
- 时长: 4 分钟
- 说明: 用填空收尾。
- 链接: 待开始
- 前置: new-1
- 分支: 终点
- 可选: 否
`

describe('challenge map DSL', () => {
  it('reads titles, types, links and status from the map text', () => {
    const map = parseChallengeMapDsl(DSL)
    expect(map.title).toBe('今日闯关')
    expect(map.nodes).toHaveLength(3)
    expect(map.nodes[0]).toMatchObject({
      id: 'review-1',
      title: '复习回廊',
      typeLabel: '复习',
      questionType: '翻卡记忆',
      statusKey: 'unlocked',
      minutes: 8,
      link: '/memory?module=flashcard',
      next: ['new-1'],
    })
    expect(map.nodes[2].statusKey).toBe('locked')
    expect(map.nodes[2].next).toEqual([])
  })

  it('keeps branch-only fields such as 可选', () => {
    const map = parseChallengeMapDsl(`${DSL}
## [side-1] 可选支线
- 前置: boss-1
- 可选: 是
`)
    expect(map.nodes[3].optional).toBe(true)
    expect(map.nodes[3].previous).toEqual(['boss-1'])
  })
})
