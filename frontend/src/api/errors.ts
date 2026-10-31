export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: unknown
  readonly requestId: string | null
  readonly retryable: boolean

  constructor(
    status: number,
    code: string,
    message: string,
    details: unknown = null,
    requestId: string | null = null,
    retryable = false,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
    this.requestId = requestId
    this.retryable = retryable
    Object.setPrototypeOf(this, ApiError.prototype)
  }
}

export class ContractError extends Error {
  readonly code = 'API_CONTRACT_MISMATCH'

  constructor(message: string) {
    super(message)
    this.name = 'ContractError'
    Object.setPrototypeOf(this, ContractError.prototype)
  }
}

export interface ErrorPresentation {
  title: string
  message: string
  requestId: string | null
  retryable: boolean
}

export interface FieldIssue {
  path: string
  message: string
}

/**
 * Validation issues the server reported for a 422, or an empty array.
 *
 * Typed here rather than in the form so every surface renders the same list and
 * no view re-implements payload parsing.
 */
export function fieldIssues(error: unknown): FieldIssue[] {
  if (!isApiError(error) || error.status !== 422) {
    return []
  }
  const details = error.details
  if (typeof details !== 'object' || details === null || !('issues' in details)) {
    return []
  }
  const issues = (details as { issues: unknown }).issues
  if (!Array.isArray(issues)) {
    return []
  }
  return issues.flatMap((issue) => {
    if (typeof issue !== 'object' || issue === null) {
      return []
    }
    const candidate = issue as { path?: unknown; message?: unknown }
    if (typeof candidate.message !== 'string') {
      return []
    }
    return [{
      path: typeof candidate.path === 'string' ? candidate.path : '',
      message: candidate.message,
    }]
  })
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

export function isContractError(error: unknown): error is ContractError {
  return error instanceof ContractError
}

export function toErrorPresentation(error: unknown): ErrorPresentation {
  if (isApiError(error)) {
    if (error.code === 'NETWORK_ERROR') {
      return {
        title: '暂时无法连接学习服务',
        message: '请检查网络连接，稍后重试。你的学习记录不会因此丢失。',
        requestId: error.requestId,
        retryable: true,
      }
    }

    if (error.code === 'AI_PROVIDER_UNAVAILABLE') {
      return {
        title: 'AI 服务还没有准备好',
        message: '请到“设置 → AI 配置”添加并启用 AI 提供商后再试。',
        requestId: error.requestId,
        retryable: true,
      }
    }

    if (error.code === 'AI_QUOTA_EXHAUSTED') {
      return {
        title: '今天的 AI 次数已用完',
        message: '按当前额度今天不能再生成新的题目或地图，明天会恢复；也可以到“设置 → AI 配置”切换成其他提供商。',
        requestId: error.requestId,
        retryable: false,
      }
    }

    if (error.code === 'AUTH_INVALID_CREDENTIALS') {
      return {
        title: '用户名或密码不正确',
        message: '请检查用户名和密码后重试。',
        requestId: error.requestId,
        retryable: false,
      }
    }

    if ([502, 503, 504].includes(error.status)) {
      return {
        title: '学习服务暂不可用',
        message: '服务正在恢复中，请稍后重试。',
        requestId: error.requestId,
        retryable: true,
      }
    }

    if (error.status === 429) {
      return {
        title: '请求过于频繁',
        message: `${error.message} 请稍后再试，不要连续重复提交。`,
        requestId: error.requestId,
        retryable: true,
      }
    }

    if (error.status === 403) {
      return {
        title: '权限不足或操作被拒绝',
        message: '当前操作无法完成，请确认账号状态后重试。',
        requestId: error.requestId,
        retryable: false,
      }
    }

    if (error.status === 404) {
      return {
        title: '这项内容暂时不可用',
        message: '目标内容可能已删除，或当前账号无权查看。',
        requestId: error.requestId,
        retryable: false,
      }
    }

    if (error.status === 409) {
      return {
        title: '当前状态不允许此操作',
        message: '内容状态刚刚发生变化，请刷新后再试。',
        requestId: error.requestId,
        retryable: false,
      }
    }

    if (error.status === 410) {
      return {
        title: '预览或下载已过期',
        message: '这次预览或下载已经失效，请重新发起。',
        requestId: error.requestId,
        retryable: false,
      }
    }

    if (error.status === 413) {
      return {
        title: '文件超过服务端限制',
        message: '文件太大，请缩小后重新上传。',
        requestId: error.requestId,
        retryable: false,
      }
    }

    if (error.status === 422) {
      // The server rejected the payload. Its issue messages stay verbatim, but
      // the learner needs one sentence saying the input (not the service) is at
      // fault, plus the request id support will ask for.
      return {
        title: '提交内容有误',
        message: fieldIssues(error).length > 0
          ? '请根据字段提示修改后重试。'
          : '请检查填写内容后重试。',
        requestId: error.requestId,
        retryable: false,
      }
    }

    if (error.status === 415) {
      return {
        title: '文件格式或媒体类型不受支持',
        message: '请使用 CSV、JSON 或 TXT 文件重新上传。',
        requestId: error.requestId,
        retryable: false,
      }
    }

    if (error.status === 401) {
      return {
        title: '认证状态已失效',
        message: '当前登录状态已失效，请重新登录。',
        requestId: error.requestId,
        retryable: false,
      }
    }

    return {
      title: '请求没有完成',
      message: '服务暂时无法处理这次操作，请稍后重试。',
      requestId: error.requestId,
      retryable: error.retryable,
    }
  }

  if (isContractError(error)) {
    return {
      title: '页面暂时无法完成这次请求',
      message: '服务返回了无法识别的数据，请刷新页面后重试。',
      requestId: null,
      retryable: false,
    }
  }

  if (error instanceof Error) {
    return {
      title: '发生未预期错误',
      message: error.message,
      requestId: null,
      retryable: false,
    }
  }

  return {
    title: '发生未预期错误',
    message: '没有收到可识别的错误信息。',
    requestId: null,
    retryable: false,
  }
}
