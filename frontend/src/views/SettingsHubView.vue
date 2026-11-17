<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'

/**
 * The settings pages share one wrapper. The knowledge base is filed under
 * them, but it is a library rather than a form: it keeps its own flat look,
 * so it does not take the settings page's class — and with it, none of the
 * carved field materials those pages are drawn with.
 */
const route = useRoute()
const isKnowledge = computed(() => route.path.startsWith('/settings/knowledge'))
</script>

<template>
  <article class="workspace-page" :class="isKnowledge ? 'ia-kb-page' : 'ia-settings-hub'">
    <RouterView />
  </article>
</template>
