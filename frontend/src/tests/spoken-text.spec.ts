import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SpokenText from '../components/SpokenText.vue'

describe('spoken text', () => {
  it('marks the wordbook words and keeps the rest untouched', () => {
    const wrapper = mount(SpokenText, {
      props: { text: '今天学习 achieve your goal.', highlight: ['achieve', 'your', 'goal'] },
    })
    expect(wrapper.findAll('.spoken-word--target').map((node) => node.text())).toEqual(['achieve', 'your', 'goal'])
    expect(wrapper.text()).toBe('今天学习 achieve your goal.')
  })

  it('leaves a passage with no wordbook words completely plain', () => {
    const wrapper = mount(SpokenText, { props: { text: '今天学习 achieve your goal.' } })
    // Nothing to study in it: the passage is text, not a row of buttons.
    expect(wrapper.findAll('.spoken-word').length).toBe(0)
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
