import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import GoalRing from '../components/ui/GoalRing.vue'
import CommandPalette from '../components/ui/CommandPalette.vue'
import { useToast } from '../composables/useToast'

const push = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))

describe('game UI kit', () => {
  beforeEach(() => {
    push.mockReset()
    document.body.innerHTML = ''
  })

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

  it('opens the command palette with Ctrl+K and filters to a route', async () => {
    const wrapper = mount(CommandPalette, { attachTo: document.body })
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))
    await nextTick()
    await nextTick()

    const items = document.body.querySelectorAll('.cmdk-item')
    expect(items.length).toBeGreaterThan(4)

    const input = document.body.querySelector('.cmdk-input') as HTMLInputElement
    input.value = '词书'
    input.dispatchEvent(new Event('input'))
    await nextTick()
    await nextTick()

    const filtered = document.body.querySelectorAll('.cmdk-item')
    expect(filtered).toHaveLength(1)
    expect(filtered[0].textContent).toContain('词书')

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    await nextTick()
    expect(push).toHaveBeenCalledWith('/wordbooks')
    wrapper.unmount()
  })
})
