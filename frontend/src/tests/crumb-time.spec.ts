import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { defineComponent, ref } from 'vue'
import CrumbTime from '../components/ui/CrumbTime.vue'

function mountTime(value: string | null = '06:30') {
  return mount(CrumbTime, { props: { modelValue: value } })
}

function inputOf(wrapper: ReturnType<typeof mountTime>): HTMLInputElement {
  return wrapper.get('input').element as HTMLInputElement
}

describe('CrumbTime', () => {
  it('shows the stored value and marks both wheels', () => {
    const wrapper = mountTime()
    expect(inputOf(wrapper).value).toBe('06:30')
    expect(wrapper.findAll('.crumb-time__cell.is-active').map((cell) => cell.text())).toEqual(['06', '30'])
  })

  it('accepts an empty value without inventing one', () => {
    const wrapper = mountTime(null)
    expect(inputOf(wrapper).value).toBe('')
    expect(wrapper.findAll('.crumb-time__cell.is-active')).toHaveLength(0)
  })

  it('is a readout, not a text box: the wheels are how a time is chosen', async () => {
    const wrapper = mountTime('06:30')
    const input = wrapper.get('input')

    expect(input.attributes('readonly')).toBeDefined()
    expect(inputOf(wrapper).value).toBe('06:30')

    // Typing into a read-only input changes nothing, in the box or the model.
    inputOf(wrapper).value = '09:30'
    await input.trigger('input')
    await input.trigger('blur')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('changes one wheel without touching the other', async () => {
    // A controlled field, so the second click has to see the first one's value.
    const value = ref<string | null>('06:30')
    const wrapper = mount(defineComponent({
      components: { CrumbTime },
      setup: () => ({ value }),
      template: '<CrumbTime v-model="value" />',
    }))

    const cells = wrapper.findAll('.crumb-time__cell')
    // The hour wheel is the first 24 cells, minutes follow.
    await cells.at(9)!.trigger('click')
    expect(value.value).toBe('09:30')

    await cells.at(24 + 11)!.trigger('click')
    expect(value.value).toBe('09:55')
  })
})
