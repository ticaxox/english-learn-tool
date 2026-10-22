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
