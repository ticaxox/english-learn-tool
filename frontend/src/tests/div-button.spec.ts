import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { defineComponent, ref } from 'vue'
import DivButton from '../components/DivButton.vue'

describe('DivButton', () => {
  it('emits click from pointer and keyboard and blocks disabled', async () => {
    const onClick = vi.fn()
    const disabled = ref(false)
    const wrapper = mount(defineComponent({
      components: { DivButton },
      setup: () => ({ onClick, disabled }),
      template: '<DivButton :disabled="disabled" @click="onClick">Go</DivButton>',
    }))
    const root = wrapper.get('[role="button"]')
    await root.trigger('click')
    expect(onClick).toHaveBeenCalledTimes(1)
    await root.trigger('keydown', { key: 'Enter' })
    expect(onClick).toHaveBeenCalledTimes(2)
    disabled.value = true
    await wrapper.vm.$nextTick()
    await root.trigger('click')
    expect(onClick).toHaveBeenCalledTimes(2)
  })

  it('submits its form from the keyboard', async () => {
    const onSubmit = vi.fn((event: Event) => event.preventDefault())
    const wrapper = mount(defineComponent({
      components: { DivButton },
      setup: () => ({ onSubmit }),
      template: '<form @submit.prevent="onSubmit"><DivButton type="submit">Go</DivButton></form>',
    }))
    await wrapper.get('[role="button"]').trigger('keydown', { key: 'Enter' })
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })
})
