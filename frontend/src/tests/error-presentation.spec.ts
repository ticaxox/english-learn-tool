import { describe, expect, it } from 'vitest'
import { ApiError, toErrorPresentation } from '../api/errors'

describe('error presentation', () => {
  it('explains a service outage in product language', () => {
    const presentation = toErrorPresentation(
      new ApiError(502, 'HTTP_502', 'Bad Gateway', null, 'gateway-request', true),
    )

    expect(presentation).toEqual({
      title: '学习服务暂不可用',
      message: '服务正在恢复中，请稍后重试。',
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
    expect(forbidden.message).not.toContain('CSRF')
  })

  it('sends an unavailable AI provider to personal settings', () => {
    const presentation = toErrorPresentation(
      new ApiError(503, 'AI_PROVIDER_UNAVAILABLE', 'No enabled AI provider is available.', null, 'ai-request', true),
    )
    expect(presentation.message).toContain('设置 → AI 配置')
    expect(presentation.message).not.toContain('No enabled AI provider')
  })

  it('describes invalid credentials without presenting a session failure', () => {
    const presentation = toErrorPresentation(
      new ApiError(401, 'AUTH_INVALID_CREDENTIALS', 'Invalid credentials.', null, 'login-request'),
    )
    expect(presentation).toMatchObject({
      title: '用户名或密码不正确',
      message: '请检查用户名和密码后重试。',
      retryable: false,
    })
  })
})
