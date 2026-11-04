import { describe, expect, it } from 'vitest'
import { ApiError, ValidationError, toErrorPresentation } from '../api/errors'

describe('error presentation', () => {
  it('keeps client-side form checks out of the unexpected-error bucket', () => {
    const presentation = toErrorPresentation(new ValidationError('两次输入的新密码不一致。'))
    expect(presentation).toEqual({
      title: '请检查填写内容',
      message: '两次输入的新密码不一致。',
      requestId: null,
      retryable: false,
    })
  })

  it('explains an unusable AI result without leaking internals', () => {
    const presentation = toErrorPresentation(
      new ApiError(500, 'AI_OUTPUT_INVALID', 'AI output did not match schema', null, 'ai-job-request', true),
    )

    expect(presentation).toMatchObject({
      title: 'AI 这次没有给出可用的结果',
      requestId: 'ai-job-request',
      retryable: true,
    })
    expect(presentation.message).not.toContain('schema')
  })

  it('explains username conflicts in product language', () => {
    const taken = toErrorPresentation(new ApiError(409, 'USERNAME_TAKEN', 'taken', null, 'r1', false))
    const unchanged = toErrorPresentation(new ApiError(422, 'USERNAME_UNCHANGED', 'same', null, 'r2', false))
    expect(taken.title).toBe('这个用户名已被使用')
    expect(unchanged.title).toBe('用户名没有变化')
  })

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
