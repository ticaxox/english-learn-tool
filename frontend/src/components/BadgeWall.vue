<script setup lang="ts">
/**
 * Every badge, earned or not, so progress is visible even before it unlocks.
 */
import { computed, onMounted, ref } from 'vue'
import ErrorNotice from './ErrorNotice.vue'
import { fetchBadges, type Badge } from '../api/progress'

const badges = ref<Badge[]>([])
const error = ref<unknown>(null)
const loading = ref(false)

const unlocked = computed(() => badges.value.filter((badge) => badge.unlocked).length)

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    badges.value = await fetchBadges()
  } catch (loadError) {
    error.value = loadError
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="badge-wall" aria-labelledby="badge-wall-title">
    <header class="badge-wall__head">
      <div>
        <h3 id="badge-wall-title">成就徽章</h3>
        <p class="field-hint">
          已解锁 {{ unlocked }} / {{ badges.length }}
        </p>
      </div>
    </header>

    <ErrorNotice v-if="error" :error="error" retry-label="重新读取" @retry="load" />

    <ul v-else-if="badges.length" class="badge-grid" aria-label="徽章">
      <li
        v-for="badge in badges"
        :key="badge.key"
        class="badge"
        :class="{ 'is-locked': !badge.unlocked }"
      >
        <span class="badge__mark" aria-hidden="true">{{ badge.unlocked ? '★' : '☆' }}</span>
        <strong>{{ badge.name }}</strong>
        <small>{{ badge.description }}</small>
      </li>
    </ul>
    <p v-else-if="!loading" class="field-hint">还没有可展示的徽章。</p>
  </section>
</template>
