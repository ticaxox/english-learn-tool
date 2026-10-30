import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import GoalRing from '../components/ui/GoalRing.vue'
import { useToast } from '../composables/useToast'

describe('game UI kit', () => {
  it('draws the goal ring from real values and clamps overflow', () => {
    const half = mount(GoalRing, { props: { value: 4, max: 8, size: 100, stroke: 10 } })
    const full = mount(GoalRing, { props: { value: 12, max: 8 } })

    const halfDash = half.find('.goal-ring__value').attributes('stroke-dasharray') ?? ''
    const fullDash = full.find('.goal-ring__value').attributes('stroke-dasharray') ?? ''
    const halfRatio = Number(halfDash.split(' ')[0]) / Number(halfDash.split(' ')[1])
    const fullRatio = Number(fullDash.split(' ')[0]) / Number(fullDash.split(' ')[1])

    expect(halfRatio).toBeCloseTo(0.5, 5)
    expect(fullRatio).toBeCloseTo(1, 5)
    expect(half.text()).toContain('4')
    expect(half.text()).toContain('/8')
  })

  it('queues and dismisses toasts without losing order', () => {
    const toast = useToast()
    const first = toast.success('已保存')
    toast.error('失败了', '检查网络')

    expect(toast.toasts.value).toHaveLength(2)
    expect(toast.toasts.value[0].title).toBe('已保存')
    expect(toast.toasts.value[1].tone).toBe('error')

    toast.dismiss(first)
    expect(toast.toasts.value).toHaveLength(1)
    expect(toast.toasts.value[0].title).toBe('失败了')
    toast.dismiss(toast.toasts.value[0].id)
    expect(toast.toasts.value).toHaveLength(0)
  })
})
