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
})
