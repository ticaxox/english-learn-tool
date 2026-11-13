<script setup lang="ts">
/**
 * Confirming that a conversation should go.
 *
 * The browser's own confirm box is not part of this product: it ignores the
 * theme, cannot be styled, and blocks the page. This is the app's dialog —
 * backdrop, card, focus trap, Escape to close — the same shape the wordbook
 * delete uses.
 */
import { ref } from 'vue'
import { useDialogA11y } from '../composables/useDialogA11y'
import CrumbIcon from './ui/CrumbIcon.vue'

const props = defineProps<{ title: string }>()

const emit = defineEmits<{ close: []; confirm: [] }>()

const dialogRef = ref<HTMLElement | null>(null)

function close(): void {
  emit('close')
}

useDialogA11y(dialogRef, { onClose: close })
</script>

<template>
  <div class="dialog-backdrop" @click.self="close">
    <section
      ref="dialogRef"
      class="dialog-card coach-confirm"
      tabindex="-1"
      role="dialog"
      aria-modal="true"
      aria-labelledby="coach-delete-title"
      aria-describedby="coach-delete-note"
    >
      <header class="dialog-heading">
        <div>
          <p class="eyebrow">删除对话</p>
          <h2 id="coach-delete-title">删除「{{ props.title }}」？</h2>
        </div>
        <button class="coach-confirm__close" type="button" aria-label="关闭" @click="close">
          <CrumbIcon name="close" :size="18" />
        </button>
      </header>

      <p id="coach-delete-note" class="coach-confirm__note">
        这段对话会从列表里消失，记录仍留在历史里。删除后无法在界面中找回。
      </p>

      <div class="coach-confirm__actions">
        <button class="coach-confirm__cancel" type="button" @click="close">取消</button>
        <button class="coach-confirm__danger" type="button" autofocus @click="emit('confirm')">删除</button>
      </div>
    </section>
  </div>
</template>
