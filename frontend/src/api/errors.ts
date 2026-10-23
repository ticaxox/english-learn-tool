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
        title: '无法连接真实学习服务',
        message: `${error.message} 请按 frontend/README.md 启动或配置后端后重试。`,
        requestId: error.requestId,
        retryable: true,
      }
    }

    if ([502, 503, 504].includes(error.status)) {
      return {
        title: '学习服务暂不可用',
        message: `${error.message} 请确认后端服务已启动且开发代理地址正确，然后重试。`,
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
        message: error.message || '服务端拒绝了本次操作，请检查账号权限、CSRF 会话或账号状态。',
        requestId: error.requestId,
        retryable: false,
      }
    }

    if (error.status === 404) {
      return {
        title: '资源不存在或不可见',
        message: error.message || '目标资源可能已删除，或当前账号无权查看。',
        requestId: error.requestId,
        retryable: false,
      }
    }

    if (error.status === 409) {
      return {
        title: '当前状态不允许此操作',
        message: error.message || '资源状态可能已变化，请刷新后重试。',
        requestId: error.requestId,
        retryable: false,
      }
    }

    if (error.status === 410) {
      return {
        title: '预览或下载已过期',
        message: error.message || '短期凭证已失效，请重新预览或创建新的导出任务。',
        requestId: error.requestId,
        retryable: false,
      }
    }

    if (error.status === 413) {
      return {
        title: '文件超过服务端限制',
        message: error.message || '请缩小文件后重新预览；服务端大小限制是最终判断。',
        requestId: error.requestId,
        retryable: false,
      }
    }

    if (error.status === 422) {
      // The server rejected the payload. Its issue messages stay verbatim, but
      // the learner needs one sentence saying the input (not the service) is at
      // fault, plus the request id support will ask for.
      return {
        title: '提交内容未通过服务端校验',
        message: fieldIssues(error).length > 0
          ? '请按下面列出的字段提示修改后重新提交；服务端校验是最终判断。'
          : (error.message || '服务端拒绝了本次提交，请检查填写内容后重试。'),
        requestId: error.requestId,
        retryable: false,
      }
    }

    if (error.status === 415) {
      return {
        title: '文件格式或媒体类型不受支持',
        message: error.message || '请使用 .csv、.json 或 .txt 文件重新预览。',
        requestId: error.requestId,
        retryable: false,
      }
    }

    if (error.status === 401) {
      return {
        title: '认证状态已失效',
        message: error.message || '当前会话无法通过认证，请重新登录。',
        requestId: error.requestId,
        retryable: false,
      }
    }

    return {
      title: `请求失败${error.status ? `（HTTP ${error.status}）` : ''}`,
      message: error.message,
      requestId: error.requestId,
      retryable: error.retryable,
    }
  }

  if (isContractError(error)) {
    return {
      title: '后端响应与前端契约不一致',
      message: error.message,
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
