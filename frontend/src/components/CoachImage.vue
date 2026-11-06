<script setup lang="ts">
/** One coach image, fetched with the bearer token and shown from a blob URL. */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { fetchCoachAttachment, type CoachAttachment } from '../api/coach'

const props = defineProps<{ attachment: CoachAttachment }>()

const src = ref<string | null>(null)
const failed = ref(false)

onMounted(async () => {
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
    <figcaption v-else class="field-hint">{{ failed ? '图片暂时无法显示' : '正在加载图片…' }}</figcaption>
  </figure>
</template>
