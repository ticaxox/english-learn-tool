import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { defineComponent, ref } from 'vue'
import CrumbDate from '../components/ui/CrumbDate.vue'

function mountDate(value: string | null = '2026-11-13') {
  return mount(CrumbDate, { props: { modelValue: value } })
}

function inputOf(wrapper: ReturnType<typeof mountDate>): HTMLInputElement {
  return wrapper.get('input').element as HTMLInputElement
}

describe('CrumbDate', () => {
  it('shows the stored date and marks it on the month', () => {
    const wrapper = mountDate()
    expect(inputOf(wrapper).value).toBe('2026-11-13')
    expect(wrapper.get('.crumb-date__month').text()).toBe('2026 年 11 月')
    const selected = wrapper.findAll('.crumb-date__cell.is-selected')
    expect(selected).toHaveLength(1)
    expect(selected[0].text()).toBe('13')
  })

  it('renders six rows of days so the panel keeps its height', () => {
    const wrapper = mountDate()
    expect(wrapper.findAll('.crumb-date__cell')).toHaveLength(42)
  })

  it('accepts an empty value without inventing one', () => {
    const wrapper = mountDate(null)
    expect(inputOf(wrapper).value).toBe('')
    expect(wrapper.findAll('.crumb-date__cell.is-selected')).toHaveLength(0)
  })

  it('puts the dashes in as the digits arrive', async () => {
    const wrapper = mountDate(null)
    const input = wrapper.get('input')
    const el = inputOf(wrapper)

    el.value = '2026'
    await input.trigger('input')
    expect(el.value).toBe('2026')

    el.value = '20261'
    await input.trigger('input')
    expect(el.value).toBe('2026-1')

    el.value = '20261113'
    await input.trigger('input')
    expect(el.value).toBe('2026-11-13')

    await input.trigger('blur')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['2026-11-13'])
  })

  it('refuses a day that does not exist and puts the stored value back', async () => {
    const wrapper = mountDate('2026-11-13')
    const input = wrapper.get('input')
    const el = inputOf(wrapper)

    el.value = '2026-02-30'
    await input.trigger('input')
    await input.trigger('blur')

    expect(el.value).toBe('2026-11-13')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('picks a day from the grid and keeps the month in view', async () => {
    const wrapper = mountDate('2026-11-13')
    const cells = wrapper.findAll('.crumb-date__cell')
    const twenty = cells.find((cell) => cell.text() === '20')
    expect(twenty).toBeTruthy()
    await twenty!.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['2026-11-20'])
  })

  it('steps a month without changing the value', async () => {
    const wrapper = mountDate('2026-11-13')
    await wrapper.get('.crumb-date__step').trigger('click')
    expect(wrapper.get('.crumb-date__month').text()).toBe('2026 年 10 月')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('clears the value from the footer', async () => {
    const wrapper = mountDate('2026-11-13')
    const quiet = wrapper.findAll('.crumb-date__action').at(1)!
    await quiet.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([null])
  })

  it('selects today from the footer', async () => {
    const value = ref<string | null>('2026-11-13')
    const wrapper = mount(defineComponent({
      components: { CrumbDate },
      setup: () => ({ value }),
      template: '<CrumbDate v-model="value" />',
    }))

    const today = new Date()
    const iso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`

    await wrapper.findAll('.crumb-date__action').at(0)!.trigger('click')
    expect(value.value).toBe(iso)
  })
})
