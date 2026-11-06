import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SpokenText from '../components/SpokenText.vue'

describe('spoken text', () => {
  it('marks English words and keeps the rest untouched', () => {
    const wrapper = mount(SpokenText, { props: { text: '今天学习 achieve your goal.' } })
    expect(wrapper.findAll('.spoken-word').map((node) => node.text())).toEqual(['achieve', 'your', 'goal'])
    expect(wrapper.text()).toBe('今天学习 achieve your goal.')
  })

  it('keeps the chosen element and its attributes', () => {
    const wrapper = mount(SpokenText, {
      props: { text: 'Read this', as: 'h3' },
      attrs: { id: 'prompt-1' },
    })
    expect(wrapper.element.tagName).toBe('H3')
    expect(wrapper.attributes('id')).toBe('prompt-1')
  })
})
