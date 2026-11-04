import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import FlashcardTrainer from '../components/FlashcardTrainer.vue'
import ChoiceTrainer from '../components/ChoiceTrainer.vue'
import SpellingTrainer from '../components/SpellingTrainer.vue'
import type {
  ChoiceQuestion,
  FlashcardQuestion,
  SpellingQuestion,
} from '../types/learning'

function flashcard(overrides: Partial<FlashcardQuestion> = {}): FlashcardQuestion {
  return {
    kind: 'flashcard',
    questionId: 'q-1',
    wordbookId: 'book-1',
    entryId: 'entry-1',
    front: 'probably',
    back: '很可能；大概',
    phonetic: '/ˈprɒbəbli/',
    partOfSpeech: 'adv.',
    example: 'She is probably right.',
    remaining: 3,
    ...overrides,
  }
}

function choice(overrides: Partial<ChoiceQuestion> = {}): ChoiceQuestion {
  return {
    kind: 'choice',
    questionId: 'q-2',
    prompt: '选择「resilient」的正确释义',
    phonetic: '/rɪˈzɪliənt/',
    options: [
      { optionId: 'o-1', label: '有弹性的；能恢复的' },
      { optionId: 'o-2', label: '沉默的' },
      { optionId: 'o-3', label: '昂贵的' },
      { optionId: 'o-4', label: '临时的' },
    ],
    optionCount: 4,
    remaining: 5,
    ...overrides,
  }
}

function spelling(overrides: Partial<SpellingQuestion> = {}): SpellingQuestion {
  return {
    kind: 'spelling',
    questionId: 'q-3',
    definition: 'n. 机会；可能性',
    phonetic: '/ˌɒpəˈtjuːnəti/',
    blankType: 'first_letter',
    cloze: 'o________',
    blanks: [
      { index: 0, prefilled: true, character: 'o' },
      { index: 1, prefilled: false, character: null },
      { index: 2, prefilled: false, character: null },
    ],
    remaining: 2,
    ...overrides,
  }
}

describe('FlashcardTrainer', () => {
  it('does not render the back of the card before an explicit flip', () => {
    const wrapper = mount(FlashcardTrainer, { props: { question: flashcard() } })
    expect(wrapper.html()).toContain('probably')
    // The answer must not exist anywhere in the DOM, not merely be hidden.
    expect(wrapper.html()).not.toContain('很可能')
    expect(wrapper.text()).not.toContain('很可能')
    expect(wrapper.html()).not.toContain('She is probably right.')
  })

  it('reveals the back only after the card is pressed', async () => {
    const wrapper = mount(FlashcardTrainer, { props: { question: flashcard() } })
    await wrapper.get('[role="button"].study-card').trigger('click')

    expect(wrapper.text()).toContain('很可能')
    expect(wrapper.emitted('reveal')).toHaveLength(1)
  })

  it('offers no rating buttons before the flip, so a rating cannot be guessed', () => {
    const wrapper = mount(FlashcardTrainer, { props: { question: flashcard() } })
    const labels = wrapper.findAll('[role="button"]').map((button) => button.text())
    expect(labels.some((label) => label.includes('无印象'))).toBe(false)
    expect(labels.some((label) => label.includes('有印象'))).toBe(false)
    expect(labels.some((label) => label.includes('已记住'))).toBe(false)
    expect(wrapper.get('.study-card').attributes('role')).toBe('button')
  })

  it('emits both documented ratings after the flip', async () => {
    const wrapper = mount(FlashcardTrainer, { props: { question: flashcard() } })
    await wrapper.get('[role="button"].study-card').trigger('click')

    const buttons = wrapper.findAll('[role="button"]')
    const again = buttons.find((button) => button.text() === '无印象')
    const good = buttons.find((button) => button.text() === '有印象')

    await again!.trigger('click')
    await good!.trigger('click')

    expect(wrapper.emitted('rate')).toEqual([['again'], ['good']])
  })

  it('emits master for the "already known" path', async () => {
    const wrapper = mount(FlashcardTrainer, { props: { question: flashcard() } })
    await wrapper.get('[role="button"].study-card').trigger('click')
    const master = wrapper.findAll('[role="button"]').find((button) => button.text() === '已记住')
    await master!.trigger('click')
    expect(wrapper.emitted('master')).toHaveLength(1)
  })

  it('re-hides the back when the question changes', async () => {
    const wrapper = mount(FlashcardTrainer, { props: { question: flashcard() } })
    await wrapper.get('[role="button"].study-card').trigger('click')
    expect(wrapper.text()).toContain('很可能')

    await wrapper.setProps({ question: flashcard({ questionId: 'q-9', front: 'seldom', back: '很少' }) })
    expect(wrapper.text()).not.toContain('很可能')
    expect(wrapper.text()).toContain('seldom')
  })

  it('moves focus to the next card so keyboard users are not stranded', async () => {
    const wrapper = mount(FlashcardTrainer, { props: { question: flashcard() }, attachTo: document.body })
    await wrapper.get('[role="button"].study-card').trigger('click')
    // Flipping unmounts the button, so focus must move to the revealed answer.
    expect(document.activeElement).toBe(wrapper.get('.study-card__back').element)

    await wrapper.setProps({ question: flashcard({ questionId: 'q-9', front: 'seldom', back: '很少' }) })
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()

    // Focus lands on the new prompt, which is programmatically focusable.
    expect(document.activeElement).toBe(wrapper.get('#flashcard-front').element)
    wrapper.unmount()
  })

  it('blocks rating while disabled', async () => {
    const wrapper = mount(FlashcardTrainer, { props: { question: flashcard(), disabled: true } })
    await wrapper.get('[role="button"].study-card').trigger('click')
    const good = wrapper.findAll('[role="button"]').find((button) => button.text() === '有印象')
    expect(good!.attributes('aria-disabled')).toBeDefined()
    await good!.trigger('click')
    expect(wrapper.emitted('rate')).toBeUndefined()
  })
})

describe('ChoiceTrainer', () => {
  it('renders exactly four options without any correctness marker', () => {
    const wrapper = mount(ChoiceTrainer, { props: { question: choice() } })
    const inputs = wrapper.findAll('input[type="radio"]')
    expect(inputs).toHaveLength(4)
    // No attribute or class may hint at the right answer.
    const html = wrapper.html().toLowerCase()
    expect(html).not.toContain('correct')
    expect(html).not.toContain('data-answer')
    expect(html).not.toContain('is-right')
  })

  it('refuses to grade a payload that is not four distinct options', async () => {
    // A duplicate label would let the learner submit the same answer twice and a
    // short list breaks the "answer is among them" promise: both are contract
    // defects, so the trainer must say so instead of rendering them.
    const wrapper = mount(ChoiceTrainer, {
      props: {
        question: choice({
          options: [
            { optionId: 'o-1', label: '有弹性的' },
            { optionId: 'o-2', label: '有弹性的' },
            { optionId: 'o-3', label: '沉默的' },
            { optionId: 'o-4', label: '昂贵的' },
          ],
        }),
      },
    })

    expect(wrapper.findAll('input[type="radio"]')).toHaveLength(0)
    expect(wrapper.text()).toContain('选项暂时不可用')
    expect(wrapper.findAll('[role="button"]')).toHaveLength(0)
  })

  it('rejects an option list that disagrees with option_count', () => {
    const wrapper = mount(ChoiceTrainer, {
      props: {
        question: choice({
          options: [
            { optionId: 'o-1', label: '有弹性的' },
            { optionId: 'o-2', label: '沉默的' },
            { optionId: 'o-3', label: '昂贵的' },
          ],
        }),
      },
    })

    expect(wrapper.findAll('input[type="radio"]')).toHaveLength(0)
    expect(wrapper.text()).toContain('选项暂时不可用')
    expect(wrapper.emitted('answer')).toBeUndefined()
  })

  it('accepts a smaller server-declared option set from a small wordbook', async () => {
    const wrapper = mount(ChoiceTrainer, {
      props: {
        question: choice({
          optionCount: 2,
          options: [
            { optionId: '有弹性的', label: '有弹性的' },
            { optionId: '沉默的', label: '沉默的' },
          ],
        }),
      },
    })
    const inputs = wrapper.findAll('input[type="radio"]')
    expect(inputs).toHaveLength(2)
    await inputs[0].setValue()
    expect(wrapper.emitted('answer')).toEqual([['有弹性的']])
  })

  it('treats options sharing one id as a contract defect', () => {
    const wrapper = mount(ChoiceTrainer, {
      props: {
        question: choice({
          options: [
            { optionId: 'o-1', label: '有弹性的' },
            { optionId: 'o-1', label: '沉默的' },
            { optionId: 'o-3', label: '昂贵的' },
            { optionId: 'o-4', label: '临时的' },
          ],
        }),
      },
    })

    expect(wrapper.findAll('input[type="radio"]')).toHaveLength(0)
    expect(wrapper.text()).toContain('选项暂时不可用')
  })

  it('sends only the chosen option id, never an answer key', async () => {
    const wrapper = mount(ChoiceTrainer, { props: { question: choice() } })
    const inputs = wrapper.findAll('input[type="radio"]')
    await inputs[2].setValue()
    expect(wrapper.emitted('answer')).toEqual([['o-3']])
  })

  it('does not emit before a choice is made', () => {
    const wrapper = mount(ChoiceTrainer, { props: { question: choice() } })
    expect(wrapper.findAll('[role="button"]')).toHaveLength(0)
    expect(wrapper.emitted('answer')).toBeUndefined()
  })

  it('is keyboard operable through native radio inputs', async () => {
    const wrapper = mount(ChoiceTrainer, { props: { question: choice() } })
    const radios = wrapper.findAll('input[type="radio"]')
    // Native radios grouped by name give arrow-key navigation for free.
    const names = new Set(radios.map((radio) => radio.attributes('name')))
    expect(names.size).toBe(1)
    for (const radio of radios) {
      expect(radio.attributes('value')).toBeTruthy()
    }
  })

  it('moves focus to the new prompt when the question changes', async () => {
    const wrapper = mount(ChoiceTrainer, { props: { question: choice() }, attachTo: document.body })
    await wrapper.findAll('input[type="radio"]')[1].setValue()

    await wrapper.setProps({ question: choice({ questionId: 'q-7', prompt: '选择「fragile」的正确释义' }) })
    await wrapper.vm.$nextTick()
    await wrapper.vm.$nextTick()

    expect(document.activeElement).toBe(wrapper.get('#choice-prompt').element)
    wrapper.unmount()
  })

  it('resets the selection when the question changes', async () => {
    const wrapper = mount(ChoiceTrainer, { props: { question: choice() } })
    await wrapper.findAll('input[type="radio"]')[0].setValue()
    expect(wrapper.emitted('answer')).toHaveLength(1)

    await wrapper.setProps({ question: choice({ questionId: 'q-8', prompt: '另一题' }) })
    expect(wrapper.findAll('input[type="radio"]')[0].attributes('checked')).toBeUndefined()
    expect(wrapper.emitted('answer')).toHaveLength(1)
  })

  it('does not answer while disabled', async () => {
    const wrapper = mount(ChoiceTrainer, { props: { question: choice(), disabled: true } })
    await wrapper.findAll('input[type="radio"]')[1].setValue()
    expect(wrapper.emitted('answer')).toBeUndefined()
  })
})

describe('SpellingTrainer', () => {
  it('renders one cell per letter and pre-fills only the revealed ones', () => {
    const wrapper = mount(SpellingTrainer, { props: { question: spelling() } })
    const cells = wrapper.findAll('.spelling-cell')
    expect(cells).toHaveLength(3)
    const prefilled = wrapper.findAll('.spelling-cell--prefilled')
    expect(prefilled).toHaveLength(1)
    expect(prefilled[0].text()).toBe('o')
  })

  it('keeps the answer out of the DOM before submission', () => {
    const wrapper = mount(SpellingTrainer, {
      props: {
        question: spelling({
          blanks: [
            { index: 0, prefilled: false, character: null },
            { index: 1, prefilled: false, character: null },
            { index: 2, prefilled: false, character: null },
          ],
        }),
      },
    })
    // Nothing beyond empty inputs may be present.
    const inputs = wrapper.findAll('input')
    expect(inputs).toHaveLength(3)
    for (const input of inputs) {
      expect((input.element as HTMLInputElement).value).toBe('')
    }
    expect(wrapper.html()).not.toContain('opportunity')
  })

  it('submits only after every editable cell is filled', async () => {
    const wrapper = mount(SpellingTrainer, { props: { question: spelling() } })
    const inputs = wrapper.findAll('input')

    await inputs[0].setValue('p')
    await inputs[0].trigger('input')
    await wrapper.vm.$nextTick()
    // One of two editable cells filled: nothing is sent yet.
    expect(wrapper.emitted('answer')).toBeUndefined()

    await inputs[1].setValue('t')
    await inputs[1].trigger('input')
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('answer')).toEqual([['opt']])
  })

  it('moves the active cell forward as each letter is typed', async () => {
    const wrapper = mount(SpellingTrainer, { props: { question: spelling() } })
    const inputs = wrapper.findAll('input')

    await inputs[0].setValue('p')
    await inputs[0].trigger('input')

    // The second editable cell becomes active, so the next keystroke lands there.
    const active = wrapper.findAll('.spelling-cell--active')
    expect(active).toHaveLength(1)
    expect((active[0].element as HTMLInputElement).value).toBe('')
  })

  it('submits automatically once every blank is filled', async () => {
    const wrapper = mount(SpellingTrainer, { props: { question: spelling() } })
    const inputs = wrapper.findAll('input')
    for (const [index, letter] of ['p', 'p'].entries()) {
      await inputs[index].setValue(letter)
      await inputs[index].trigger('input')
    }
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('answer')).toEqual([['opp']])
  })

  it('submits the concatenated answer including the prefilled letter', async () => {
    const wrapper = mount(SpellingTrainer, { props: { question: spelling() } })
    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('p')
    await inputs[0].trigger('input')
    await inputs[1].setValue('t')
    await inputs[1].trigger('input')

    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('answer')).toEqual([['opt']])
  })

  it('clears the previous letter on backspace before moving back', async () => {
    const wrapper = mount(SpellingTrainer, { props: { question: spelling() } })
    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('p')
    await inputs[0].trigger('input')
    await inputs[0].trigger('keydown', { key: 'Backspace' })

    const values = wrapper.findAll('input').map((input) => (input.element as HTMLInputElement).value)
    // The typed letter is cleared; the server-provided first letter stays.
    expect(values.join('')).toBe('')
    expect(wrapper.findAll('.spelling-cell--prefilled')[0].text()).toBe('o')
  })

  it('describes the active blanking strategy to the learner', () => {
    const wrapper = mount(SpellingTrainer, { props: { question: spelling({ blankType: 'full' }) } })
    expect(wrapper.text()).toContain('全挖空')
  })

  it('blocks submission while disabled', async () => {
    const wrapper = mount(SpellingTrainer, {
      props: {
        question: spelling({
          blanks: [
            { index: 0, prefilled: false, character: null },
            { index: 1, prefilled: false, character: null },
            { index: 2, prefilled: false, character: null },
          ],
        }),
        disabled: true,
      },
    })
    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('a')
    await inputs[0].trigger('input')
    await inputs[1].setValue('b')
    await inputs[1].trigger('input')
    await inputs[2].setValue('c')
    await inputs[2].trigger('input')

    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('answer')).toBeUndefined()
  })
})
