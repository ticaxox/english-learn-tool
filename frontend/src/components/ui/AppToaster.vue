<script setup lang="ts">
import { CheckCircle2, Info, X, XCircle } from '@lucide/vue'
import {
  ToastClose,
  ToastDescription,
  ToastProvider,
  ToastRoot,
  ToastTitle,
  ToastViewport,
} from 'reka-ui'
import { useToast, type ToastTone } from '../../composables/useToast'

const { toasts, dismiss } = useToast()

const icons = { success: CheckCircle2, error: XCircle, info: Info } as const

function iconFor(tone: ToastTone) {
  return icons[tone]
}
</script>

<template>
  <ToastProvider :duration="4200" swipe-direction="right">
    <ToastRoot
      v-for="toast in toasts"
      :key="toast.id"
      class="crumb-toast"
      :class="`crumb-toast--${toast.tone}`"
      :duration="toast.duration"
      @update:open="(open) => { if (!open) dismiss(toast.id) }"
    >
      <component :is="iconFor(toast.tone)" class="crumb-toast__icon" :size="22" aria-hidden="true" />
      <div class="crumb-toast__copy">
        <ToastTitle class="crumb-toast__title">{{ toast.title }}</ToastTitle>
        <ToastDescription v-if="toast.description" class="crumb-toast__description">
          {{ toast.description }}
        </ToastDescription>
      </div>
      <ToastClose class="crumb-toast__close" aria-label="关闭提示">
        <X :size="16" />
      </ToastClose>
    </ToastRoot>
    <ToastViewport class="crumb-toast-viewport" />
  </ToastProvider>
</template>
