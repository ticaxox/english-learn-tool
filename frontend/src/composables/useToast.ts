import { ref } from 'vue'

export type ToastTone = 'success' | 'error' | 'info'

export interface ToastItem {
  id: number
  title: string
  description?: string
  tone: ToastTone
  duration: number
}

const toasts = ref<ToastItem[]>([])
let nextId = 0

export function useToast() {
  function push(input: { title: string; description?: string; tone?: ToastTone; duration?: number }): number {
    const id = ++nextId
    const tone = input.tone ?? 'info'
    toasts.value = [
      ...toasts.value,
      {
        id,
        title: input.title,
        description: input.description,
        tone,
        // Errors need longer to read; successes get out of the way.
        duration: input.duration ?? (tone === 'error' ? 7000 : 4200),
      },
    ]
    return id
  }

  function dismiss(id: number): void {
    toasts.value = toasts.value.filter((toast) => toast.id !== id)
  }

  return {
    toasts,
    push,
    dismiss,
    success: (title: string, description?: string) => push({ title, description, tone: 'success' }),
    error: (title: string, description?: string) => push({ title, description, tone: 'error' }),
  }
}
