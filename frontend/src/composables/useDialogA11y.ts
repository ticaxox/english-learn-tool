import { nextTick, onMounted, onUnmounted, type Ref } from 'vue'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

interface DialogA11yOptions {
  onClose: () => void
}

export function useDialogA11y(
  dialogRef: Ref<HTMLElement | null>,
  options: DialogA11yOptions,
): void {
  let previouslyFocused: HTMLElement | null = null
  let previousBodyOverflow = ''

  function focusableElements(): HTMLElement[] {
    const dialog = dialogRef.value
    if (!dialog) {
      return []
    }
    return Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
      .filter((element) => element.getAttribute('aria-hidden') !== 'true')
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      event.preventDefault()
      options.onClose()
      return
    }

    if (event.key !== 'Tab') {
      return
    }

    const elements = focusableElements()
    if (elements.length === 0) {
      event.preventDefault()
      dialogRef.value?.focus()
      return
    }

    const first = elements[0]
    const last = elements[elements.length - 1]
    const active = document.activeElement

    if (!dialogRef.value?.contains(active)) {
      event.preventDefault()
      first.focus()
      return
    }

    if (event.shiftKey && active === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && active === last) {
      event.preventDefault()
      first.focus()
    }
  }

  onMounted(async () => {
    previouslyFocused = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null
    previousBodyOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', handleKeydown)

    await nextTick()
    const initialTarget = dialogRef.value?.querySelector<HTMLElement>('[data-autofocus]')
    ;(initialTarget ?? dialogRef.value)?.focus()
  })

  onUnmounted(() => {
    document.removeEventListener('keydown', handleKeydown)
    document.body.style.overflow = previousBodyOverflow
    previouslyFocused?.focus()
  })
}
