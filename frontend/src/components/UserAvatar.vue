<script setup lang="ts">
/** The learner's chosen pixel sprite. The art is local; only the key is synced. */
import { computed } from 'vue'
import bat from '../assets/avatars/bat.svg'
import candle from '../assets/avatars/candle.svg'
import candy from '../assets/avatars/candy.svg'
import cat from '../assets/avatars/cat.svg'
import ghost from '../assets/avatars/ghost.svg'
import pumpkin from '../assets/avatars/pumpkin.svg'
import skull from '../assets/avatars/skull.svg'
import witch from '../assets/avatars/witch.svg'
import type { AvatarKey } from '../api/contracts'

const props = withDefaults(defineProps<{
  avatar?: AvatarKey
  label?: string
  size?: 'small' | 'medium' | 'large'
}>(), { avatar: 'pumpkin', label: '', size: 'small' })

const sprites: Record<AvatarKey, string> = { bat, candle, candy, cat, ghost, pumpkin, skull, witch }
const source = computed(() => sprites[props.avatar] ?? pumpkin)
</script>

<template>
  <span
    class="user-avatar"
    :class="`user-avatar--${size}`"
    role="img"
    :aria-label="label || '像素头像'"
  >
    <img :src="source" alt="" />
  </span>
</template>

<style scoped>
.user-avatar {
  display: inline-grid;
  place-items: center;
  flex: 0 0 auto;
  overflow: hidden;
  border-radius: 50%;
  background: #fff;
  line-height: 0;
}

.user-avatar img {
  width: 100%;
  height: 100%;
  display: block;
  image-rendering: pixelated;
}

.user-avatar--small { width: 30px; height: 30px; }
.user-avatar--medium { width: 52px; height: 52px; }
.user-avatar--large { width: 72px; height: 72px; }
</style>
