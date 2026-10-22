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
    front: 'probably',
    back: '很可能；大概',
    phonetic: '/ˈprɒbəbli/',
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

  it('reveals the back only after the flip button is pressed', async () => {
    const wrapper = mount(FlashcardTrainer, { props: { question: flashcard() } })
    await wrapper.get('button.study-card__flip').trigger('click')

    expect(wrapper.text()).toContain('很可能')
    expect(wrapper.emitted('reveal')).toHaveLength(1)
  })

  it('offers no rating buttons before the flip, so a rating cannot be guessed', () => {
    const wrapper = mount(FlashcardTrainer, { props: { question: flashcard() } })
    const labels = wrapper.findAll('button').map((button) => button.text())
    expect(labels).toEqual(['翻到背面'])
  })

  it('emits both documented ratings after the flip', async () => {
    const wrapper = mount(FlashcardTrainer, { props: { question: flashcard() } })
    await wrapper.get('button.study-card__flip').trigger('click')

    const buttons = wrapper.findAll('button')
    const again = buttons.find((button) => button.text() === '无印象')
    const good = buttons.find((button) => button.text() === '有印象')

    await again!.trigger('click')
    await good!.trigger('click')

    expect(wrapper.emitted('rate')).toEqual([['again'], ['good']])
  })

  it('emits master for the "already known" path', async () => {
    const wrapper = mount(FlashcardTrainer, { props: { question: flashcard() } })
    await wrapper.get('button.study-card__flip').trigger('click')
    const master = wrapper.findAll('button').find((button) => button.text() === '已记住')
    await master!.trigger('click')
    expect(wrapper.emitted('master')).toHaveLength(1)
  })

  it('re-hides the back when the question changes', async () => {
    const wrapper = mount(FlashcardTrainer, { props: { question: flashcard() } })
    await wrapper.get('button.study-card__flip').trigger('click')
    expect(wrapper.text()).toContain('很可能')

    await wrapper.setProps({ question: flashcard({ questionId: 'q-9', front: 'seldom', back: '很少' }) })
    expect(wrapper.text()).not.toContain('很可能')
    expect(wrapper.text()).toContain('seldom')
  })

  it('blocks rating while disabled', async () => {
    const wrapper = mount(FlashcardTrainer, { props: { question: flashcard(), disabled: true } })
    await wrapper.get('button.study-card__flip').trigger('click')
    const good = wrapper.findAll('button').find((button) => button.text() === '有印象')
    expect(good!.attributes('disabled')).toBeDefined()
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

  it('sends only the chosen option id, never an answer key', async () => {
    const wrapper = mount(ChoiceTrainer, { props: { question: choice() } })
    const inputs = wrapper.findAll('input[type="radio"]')
    await inputs[2].setValue()
    await wrapper.findAll('button').find((button) => button.text() === '提交答案')!.trigger('click')
    expect(wrapper.emitted('answer')).toEqual([['o-3']])
  })

  it('does not emit before a choice is made', async () => {
    const wrapper = mount(ChoiceTrainer, { props: { question: choice() } })
    const submit = wrapper.findAll('button').find((button) => button.text() === '提交答案')
    expect(submit!.attributes('disabled')).toBeDefined()
    await submit!.trigger('click')
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

  it('resets the selection when the question changes', async () => {
    const wrapper = mount(ChoiceTrainer, { props: { question: choice() } })
    await wrapper.findAll('input[type="radio"]')[0].setValue()
    expect(wrapper.findAll('input[type="radio"]')[0].attributes('checked')).toBeDefined()

    await wrapper.setProps({ question: choice({ questionId: 'q-8', prompt: '另一题' }) })
    const submit = wrapper.findAll('button').find((button) => button.text() === '提交答案')
    expect(submit!.attributes('disabled')).toBeDefined()
  })

  it('prevents a second submission while disabled', async () => {
    const wrapper = mount(ChoiceTrainer, { props: { question: choice(), disabled: true } })
    await wrapper.findAll('input[type="radio"]')[1].setValue()
    const submit = wrapper.findAll('button').find((button) => button.text() === '提交答案')
    expect(submit!.attributes('disabled')).toBeDefined()
    await submit!.trigger('click')
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

  it('keeps submission blocked until every editable cell is filled', async () => {
    const wrapper = mount(SpellingTrainer, { props: { question: spelling() } })
    const submit = () => wrapper.findAll('button').find((button) => button.text() === '提交拼写')

    expect(submit()!.attributes('disabled')).toBeDefined()

    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('p')
    await inputs[0].trigger('input')
    // One of two editable cells filled: still incomplete.
    expect(submit()!.attributes('disabled')).toBeDefined()

    await inputs[1].setValue('t')
    await inputs[1].trigger('input')
    expect(submit()!.attributes('disabled')).toBeUndefined()
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

  it('enables submission once every blank is filled', async () => {
    const wrapper = mount(SpellingTrainer, { props: { question: spelling() } })
    const inputs = wrapper.findAll('input')
    for (const [index, letter] of ['p', 'p'].entries()) {
      await inputs[index].setValue(letter)
      await inputs[index].trigger('input')
    }
    const submit = wrapper.findAll('button').find((button) => button.text() === '提交拼写')
    expect(submit!.attributes('disabled')).toBeUndefined()
  })

  it('submits the concatenated answer including the prefilled letter', async () => {
    const wrapper = mount(SpellingTrainer, { props: { question: spelling() } })
    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('p')
    await inputs[0].trigger('input')
    await inputs[1].setValue('t')
    await inputs[1].trigger('input')

    await wrapper.findAll('button').find((button) => button.text() === '提交拼写')!.trigger('click')
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

    const submit = wrapper.findAll('button').find((button) => button.text() === '提交拼写')
    await submit!.trigger('click')
    expect(wrapper.emitted('answer')).toBeUndefined()
  })
})

