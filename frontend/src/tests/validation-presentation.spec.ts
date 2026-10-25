import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { ApiError, fieldIssues, toErrorPresentation } from '../api/errors'
import ErrorNotice from '../components/ErrorNotice.vue'

function validationError(issues: { path: string; message: string }[], requestId = 'req-422') {
  return new ApiError(
    422,
    'VALIDATION_ERROR',
    '提交的内容未通过服务端校验。',
    { issues: issues.map((issue) => ({ ...issue, type: 'value_error' })) },
    requestId,
    false,
  )
}

describe('422 validation presentation', () => {
  it('names the fault as a rejection of the submitted input', () => {
    const presentation = toErrorPresentation(validationError([{ path: 'daily_new_words', message: 'must be <= 100' }]))

    expect(presentation).toMatchObject({
      title: '提交内容有误',
      requestId: 'req-422',
      retryable: false,
    })
    expect(presentation.message).toContain('请根据字段提示修改后重试')
  })

  it('exposes the server issue list without rewording it', () => {
    expect(fieldIssues(validationError([{ path: 'exam_date', message: 'date must be in the future' }]))).toEqual([
      { path: 'exam_date', message: 'date must be in the future' },
    ])
  })

  it('reports no issues for errors that are not 422', () => {
    expect(fieldIssues(new ApiError(409, 'CONFLICT', '冲突', null, 'req-409'))).toEqual([])
    expect(fieldIssues(new Error('boom'))).toEqual([])
    expect(fieldIssues(null)).toEqual([])
  })

  it('ignores a 422 whose details are not the documented issue list', () => {
    const malformed = new ApiError(422, 'VALIDATION_ERROR', 'x', { issues: 'not-an-array' }, 'req-bad')
    expect(fieldIssues(malformed)).toEqual([])
    // Falls back to the server message rather than an empty explanation.
    expect(toErrorPresentation(malformed).message).toBe('x')
  })

  it('renders each server issue with its field path and keeps the request id visible', () => {
    const wrapper = mount(ErrorNotice, {
      props: {
        error: validationError([
          { path: 'daily_new_words', message: 'must be <= 100' },
          { path: 'memory_config.spelling.enabled', message: 'at least one module is required' },
        ]),
      },
    })

    const text = wrapper.text()
    expect(text).toContain('daily_new_words')
    expect(text).toContain('must be <= 100')
    expect(text).toContain('memory_config.spelling.enabled')
    expect(text).toContain('req-422')
    expect(wrapper.find('.field-issue-list').exists()).toBe(true)
    // The server's own wording stays actionable: no client-side retry is offered.
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('offers no retry for a validation rejection even when retry is requested', () => {
    const wrapper = mount(ErrorNotice, {
      props: { error: validationError([{ path: 'a', message: 'bad' }]), retryLabel: '重试' },
      listeners: { retry: vi.fn() },
    })
    expect(wrapper.find('button').exists()).toBe(false)
  })
})
