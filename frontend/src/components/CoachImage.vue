<script setup lang="ts">
/**
 * One coach attachment: images are fetched with the bearer token and shown
 * from a blob URL; documents render as a named file chip.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AppIcon from './AppIcon.vue'
import { fetchCoachAttachment, type CoachAttachment } from '../api/coach'

const props = defineProps<{ attachment: CoachAttachment }>()

const isImage = computed(() => props.attachment.contentType.startsWith('image/'))
const extension = computed(() => props.attachment.filename.split('.').pop()?.toUpperCase() ?? 'FILE')
const src = ref<string | null>(null)
const failed = ref(false)

onMounted(async () => {
  if (!isImage.value) return
  try {
    const blob = await fetchCoachAttachment(props.attachment.id)
    src.value = URL.createObjectURL(blob)
  } catch {
    failed.value = true
  }
})

onBeforeUnmount(() => {
  if (src.value) URL.revokeObjectURL(src.value)
})
</script>

<template>
  <figure class="coach-image">
    <img v-if="src" :src="src" :alt="attachment.filename" loading="lazy" />
    <span v-else-if="!isImage" class="coach-image__file">
      <AppIcon name="book" />
      <span class="coach-image__name">{{ attachment.filename }}</span>
      <span class="coach-image__ext">{{ extension }}</span>
    </span>
    <figcaption v-else class="field-hint">{{ failed ? '图片暂时无法显示' : '正在加载图片…' }}</figcaption>
  </figure>
</template>
