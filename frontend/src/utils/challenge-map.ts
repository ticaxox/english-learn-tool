/**
 * Parser for the Markdown-like daily map description.
 *
 * The server writes one `##` section per node and bullet lines for its type,
 * question link, previous node and branches. The page renders that text as a
 * clickable map instead of hard-coding station positions.
 */

export interface ChallengeMapNode {
  id: string
  title: string
  typeLabel: string
  questionType: string
  statusLabel: string
  statusKey: string
  minutes: number
  stars: number
  description: string
  link: string
  previous: string[]
  next: string[]
  optional: boolean
}

export interface ChallengeMap {
  title: string
  summary: string
  nodes: ChallengeMapNode[]
}

const STATUS_KEYS: Record<string, string> = {
  未解锁: 'locked',
  已解锁: 'unlocked',
  进行中: 'in_progress',
  已完成: 'completed',
  失败: 'failed',
}

type TextField = 'typeLabel' | 'questionType' | 'statusLabel' | 'description' | 'link'

const FIELD_ALIASES: Record<string, TextField> = {
  类型: 'typeLabel',
  题目类型: 'questionType',
  状态: 'statusLabel',
  说明: 'description',
  链接: 'link',
}

function splitLinks(value: string): string[] {
  return value
    .split(/[，,]/)
    .map((item) => item.trim())
    .filter((item) => item && item !== '开始' && item !== '终点')
}

export function parseChallengeMapDsl(text: string): ChallengeMap {
  const map: ChallengeMap = { title: '', summary: '', nodes: [] }
  let current: ChallengeMapNode | null = null

  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line) continue
    if (line.startsWith('## ')) {
      const match = line.match(/^##\s+\[([^\]]+)\]\s*(.*)$/)
      if (!match) {
        current = null
        continue
      }
      current = {
        id: match[1].trim(),
        title: match[2].trim() || match[1].trim(),
        typeLabel: '',
        questionType: '',
        statusLabel: '',
        statusKey: 'locked',
        minutes: 0,
        stars: 0,
        description: '',
        link: '',
        previous: [],
        next: [],
        optional: false,
      }
      map.nodes.push(current)
      continue
    }
    if (line.startsWith('# ')) {
      map.title = line.slice(2).trim()
      continue
    }
    if (line.startsWith('> ')) {
      map.summary = line.slice(2).trim()
      continue
    }
    if (!current || !line.startsWith('- ')) continue

    const separator = line.indexOf(':')
    if (separator === -1) continue
    const key = line.slice(2, separator).trim()
    const value = line.slice(separator + 1).trim()

    if (key === '时长') {
      current.minutes = Number.parseInt(value, 10) || 0
      continue
    }
    if (key === '前置') {
      current.previous = splitLinks(value)
      continue
    }
    if (key === '分支') {
      current.next = splitLinks(value)
      continue
    }
    if (key === '星数') {
      current.stars = Math.max(0, Math.min(3, Number.parseInt(value, 10) || 0))
      continue
    }
    if (key === '可选') {
      current.optional = value === '是'
      continue
    }
    const field = FIELD_ALIASES[key]
    if (field) {
      current[field] = value
    }
  }

  for (const node of map.nodes) {
    node.statusKey = STATUS_KEYS[node.statusLabel] ?? 'locked'
  }
  return map
}

/**
 * Horizontal gap between the main stops when the map should fill its card.
 * Falls back to the minimum gap before the container has been measured.
 */
export function spreadSpacing(available: number, count: number, node = 96, minimum = 146): number {
  if (count <= 1 || available <= 0) return minimum
  return Math.max(minimum, (available - node - 20) / (count - 1))
}
