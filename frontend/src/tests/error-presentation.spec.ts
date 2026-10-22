import { describe, expect, it } from 'vitest'
import { ApiError, toErrorPresentation } from '../api/errors'

describe('error presentation', () => {
  it('explains a proxy or gateway outage without implying a fake service', () => {
    const presentation = toErrorPresentation(
      new ApiError(502, 'HTTP_502', 'Bad Gateway', null, 'gateway-request', true),
    )

    expect(presentation).toEqual({
      title: '学习服务暂不可用',
      message: 'Bad Gateway 请确认后端服务已启动且开发代理地址正确，然后重试。',
      requestId: 'gateway-request',
      retryable: true,
    })
  })
  it('makes throttling and server-side permission rejection explicit', () => {
    const throttled = toErrorPresentation(
      new ApiError(429, 'AUTH_THROTTLED', '登录尝试次数过多。', null, 'rate-limit-request'),
    )
    const forbidden = toErrorPresentation(
      new ApiError(403, 'AUTH_CSRF_INVALID', 'CSRF validation failed.', null, 'csrf-request'),
    )

    expect(throttled).toMatchObject({
      title: '请求过于频繁',
      requestId: 'rate-limit-request',
      retryable: true,
    })
    expect(forbidden).toMatchObject({
      title: '权限不足或操作被拒绝',
      requestId: 'csrf-request',
      retryable: false,
    })
  })
})
