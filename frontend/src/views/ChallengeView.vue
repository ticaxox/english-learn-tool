<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import ErrorNotice from '../components/ErrorNotice.vue'
import LoadingState from '../components/LoadingState.vue'
import ChallengeBossPanel from '../components/ChallengeBossPanel.vue'
import {
  CHALLENGE_NODE_LABELS,
  CHALLENGE_STATUS_LABELS,
  generateTodayChallenge,
  getChallenge,
  getChallengeHistory,
  getChallengeJob,
  getChallengeNodeDetail,
  getTodayChallenge,
  startChallengeNode,
  type ChallengeBossResult,
  type ChallengeHistoryItem,
  type ChallengeNode,
  type ChallengeNodeDetail,
  type ChallengePlan,
} from '../api/challenge'
import { isApiError } from '../api/errors'
import '../challenge.css'

const route = useRoute()
const router = useRouter()

const PLAN_STATUS_LABELS = {
  generating: '生成中',
  ready: '进行中',
  failed: '生成失败',
  completed: '已完成',
  expired: '已过期',
}

const plan = ref<ChallengePlan | null>(null)
const loading = ref(true)
const error = ref<unknown>(null)
const notGenerated = ref(false)
const generating = ref(false)
const generationError = ref<unknown>(null)
const generationStatus = ref('')

const selectedNode = ref<ChallengeNodeDetail | null>(null)
const nodeLoading = ref(false)
const nodeError = ref<unknown>(null)
const nodeStarting = ref(false)
const bossSession = ref<{ nodeId: string; sessionId: string } | null>(null)
const planRefreshError = ref<unknown>(null)

const historyItems = ref<ChallengeHistoryItem[]>([])
const historyOffset = ref(0)
const historyHasMore = ref(false)
const historyLoading = ref(false)
const historyError = ref<unknown>(null)

const routeChallengeId = computed(() => typeof route.params.challengeId === 'string' ? route.params.challengeId : null)
const mainNodes = computed(() => (plan.value?.nodes ?? [])
  .filter((node) => !node.optional)
  .sort((left, right) => left.orderIndex - right.orderIndex))
const optionalNodes = computed(() => (plan.value?.nodes ?? []).filter((node) => node.optional))
const todayLocalDate = computed(() => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(new Date()))
const readOnly = computed(() =>
  Boolean(plan.value && (plan.value.status === 'expired' || plan.value.localDate < todayLocalDate.value)),
)
const progressPercent = computed(() => {
  if (!plan.value || plan.value.mainTotal <= 0) return 0
  return Math.min(100, Math.round((plan.value.mainCompleted / plan.value.mainTotal) * 100))
})

function isNotGenerated(errorValue: unknown): boolean {
  return isApiError(errorValue)
    && (errorValue.code === 'CHALLENGE_NOT_GENERATED' || errorValue.status === 404)
}

function nodeStatusClass(node: ChallengeNode): string {
  return `challenge-node--${node.status}`
}

function memoryModule(node: ChallengeNode): string {
  if (node.nodeType === 'NEW_WORDS') return 'flashcard'
  if (node.nodeType === 'WORD_DRILL') {
    return node.practiceSpec.drill_mode === 'spelling' ? 'spelling' : 'choice'
  }
  return 'choice'
}

function nodeActionLabel(node: ChallengeNode): string {
  if (node.status === 'locked') return '查看锁定原因'
  if (node.status === 'in_progress') return '继续任务'
  if (node.status === 'completed') return '查看结果'
  if (node.status === 'failed') return '重新开始'
  return '开始节点'
}

async function fetchPlan(): Promise<ChallengePlan> {
  return routeChallengeId.value
    ? await getChallenge(routeChallengeId.value)
    : await getTodayChallenge()
}

async function loadPlan(): Promise<void> {
  loading.value = true
  error.value = null
  notGenerated.value = false
  planRefreshError.value = null
  try {
    plan.value = await fetchPlan()
    if (selectedNode.value) selectedNode.value = null
  } catch (requestError) {
    if (!routeChallengeId.value && isNotGenerated(requestError)) {
      plan.value = null
      notGenerated.value = true
    } else {
      plan.value = null
      error.value = requestError
    }
  } finally {
    loading.value = false
  }
}

async function refreshPlanSilently(): Promise<void> {
  planRefreshError.value = null
  try {
    plan.value = await fetchPlan()
    if (selectedNode.value) selectedNode.value = null
  } catch (requestError) {
    planRefreshError.value = requestError
  }
}

async function generateMap(): Promise<void> {
  if (generating.value) return
  generating.value = true
  generationError.value = null
  generationStatus.value = '正在生成今日地图…'
  try {
    const accepted = await generateTodayChallenge()
    if (accepted.status === 'ready' || accepted.status === 'completed' || !accepted.jobId) {
      await loadPlan()
      return
    }
    for (let attempt = 0; attempt < 120; attempt += 1) {
      generationStatus.value = '地图生成中…'
      await new Promise((resolve) => window.setTimeout(resolve, 1000))
      const job = await getChallengeJob(accepted.jobId)
      generationStatus.value = `地图生成中，任务状态：${job.status}`
      if (job.status === 'succeeded') {
        await loadPlan()
        return
      }
      if (job.status === 'failed' || job.status === 'cancelled') {
        generationError.value = new Error(job.errorMessage || 'AI 地图生成失败，请重试或使用传统学习模式。')
        return
      }
    }
    generationError.value = new Error('地图生成等待超时，页面不会生成替代地图。')
  } catch (requestError) {
    generationError.value = requestError
  } finally {
    generating.value = false
  }
}

async function openNode(node: ChallengeNode): Promise<void> {
  if (!plan.value) return
  nodeLoading.value = true
  nodeError.value = null
  try {
    selectedNode.value = await getChallengeNodeDetail(plan.value.id, node.id)
  } catch (requestError) {
    nodeError.value = requestError
  } finally {
    nodeLoading.value = false
  }
}

async function startNode(detail: ChallengeNodeDetail): Promise<void> {
  if (!plan.value || readOnly.value || nodeStarting.value) return
  if (!detail.allowedActions.includes('start') && !detail.allowedActions.includes('resume')) return
  nodeStarting.value = true
  nodeError.value = null
  try {
    const started = await startChallengeNode(plan.value.id, detail.node.id)
    if (!started.resourceId) {
      await loadPlan()
      return
    }
    if (started.resourceType === 'memory') {
      await router.push({
        name: 'memory',
        query: {
          sessionId: started.resourceId,
          module: memoryModule(detail.node),
          challengeId: plan.value.id,
          nodeId: detail.node.id,
        },
      })
      return
    }
    if (detail.node.nodeType === 'BOSS') {
      bossSession.value = { nodeId: detail.node.id, sessionId: started.resourceId }
      selectedNode.value = null
      return
    }
    await router.push(`/practice/${encodeURIComponent(started.resourceId)}`)
  } catch (requestError) {
    nodeError.value = requestError
  } finally {
    nodeStarting.value = false
  }
}

async function viewResult(detail: ChallengeNodeDetail): Promise<void> {
  if (!plan.value || !detail.node.resourceId) return
  if (detail.node.resourceType === 'memory') {
    await router.push({
      name: 'memory',
      query: {
        sessionId: detail.node.resourceId,
        module: memoryModule(detail.node),
        challengeId: plan.value.id,
        nodeId: detail.node.id,
      },
    })
  } else {
    await router.push(`/practice/${encodeURIComponent(detail.node.resourceId)}`)
  }
}

async function loadHistory(reset = true): Promise<void> {
  if (historyLoading.value) return
  historyLoading.value = true
  historyError.value = null
  if (reset) {
    historyItems.value = []
    historyOffset.value = 0
    historyHasMore.value = false
  }
  try {
    const page = await getChallengeHistory(20, historyOffset.value)
    historyItems.value = reset ? page.items : [
      ...historyItems.value,
      ...page.items.filter((item) => !historyItems.value.some((current) => current.id === item.id)),
    ]
    historyHasMore.value = page.hasMore
    historyOffset.value = page.nextCursor && /^\d+$/.test(page.nextCursor)
      ? Number(page.nextCursor)
      : historyOffset.value + page.items.length
  } catch (requestError) {
    historyError.value = requestError
  } finally {
    historyLoading.value = false
  }
}

function onBossCompleted(_result: ChallengeBossResult): void {
  void refreshPlanSilently()
  void loadHistory(true)
}

watch(routeChallengeId, () => {
  bossSession.value = null
  void loadPlan()
})

onMounted(() => {
  void loadPlan()
  void loadHistory(true)
})
</script>

<template>
  <article class="challenge-page">
    <header class="challenge-hero">
      <div>
        <p class="eyebrow">每日闯关</p>
        <h1>{{ plan?.title || '今天的学习地图' }}</h1>
        <p class="lead">按顺序完成，最后挑战终点。</p>
      </div>
      <div class="challenge-hero__actions">
        <RouterLink class="button-secondary" to="/overview">返回今日学习</RouterLink>
        <button class="button-secondary" type="button" :disabled="loading || generating" @click="loadPlan">刷新地图</button>
      </div>
    </header>

    <LoadingState v-if="loading" label="正在加载地图…" />
    <ErrorNotice v-else-if="error" :error="error" retry-label="重新读取地图" @retry="loadPlan" />

    <section v-else-if="notGenerated" class="panel challenge-generate" aria-labelledby="challenge-generate-title">
      <div class="challenge-generate__mark" aria-hidden="true">✦</div>
      <div>
        <p class="eyebrow">今日路线</p>
        <h2 id="challenge-generate-title">今天的地图还没有生成</h2>
        <p>生成一条今天的学习路线。</p>
        <ErrorNotice v-if="generationError" :error="generationError" :show-retry="false" />
        <div class="button-row">
          <button class="button" type="button" :disabled="generating" @click="generateMap">
            {{ generating ? '正在生成…' : '生成今日地图' }}
          </button>
          <RouterLink class="button-secondary" to="/overview">先学习今日任务</RouterLink>
        </div>
        <p v-if="generating" class="inline-note" role="status">{{ generationStatus }}</p>
      </div>
    </section>

    <template v-else-if="plan">
      <section class="panel challenge-summary" aria-label="今日闯关摘要">
        <div class="challenge-summary__copy">
          <p class="eyebrow">{{ plan.localDate }} · {{ PLAN_STATUS_LABELS[plan.status] }}</p>
          <h2>{{ plan.summary || '按顺序完成，最后挑战终点。' }}</h2>
          <p class="field-hint">预计 {{ plan.targetMinutes }} 分钟 · 主线 {{ plan.mainCompleted }} / {{ plan.mainTotal }}</p>
        </div>
        <div class="challenge-progress" role="progressbar" :aria-valuenow="progressPercent" aria-valuemin="0" aria-valuemax="100">
          <span :style="{ width: `${progressPercent}%` }"></span>
        </div>
      </section>

      <div v-if="readOnly" class="alert alert-warning" role="status">
        <strong>跨日地图只读</strong>
        <p>这份地图已过期，只能查看结果。</p>
      </div>

      <section v-if="plan.status === 'failed'" class="panel">
        <ErrorNotice :error="{ code: plan.errorCode, message: plan.errorMessage || '今日地图生成失败。' }" :show-retry="false" />
        <div class="button-row">
          <button class="button" type="button" :disabled="generating" @click="generateMap">重试生成</button>
          <RouterLink class="button-secondary" to="/overview">使用传统学习</RouterLink>
        </div>
        <p v-if="generationError" class="field-error">{{ generationError }}</p>
      </section>

      <section class="challenge-map" aria-labelledby="challenge-map-title">
        <div class="challenge-map__heading">
          <div><p class="eyebrow">主线</p><h2 id="challenge-map-title">今日主线</h2></div>
          <span class="challenge-map__progress">{{ plan.mainCompleted }} / {{ plan.mainTotal }}</span>
        </div>
        <div class="challenge-path">
          <article v-for="(node, index) in mainNodes" :key="node.id" class="challenge-node" :class="[nodeStatusClass(node), { 'challenge-node--boss': node.nodeType === 'BOSS' }]">
            <div class="challenge-node__marker" aria-hidden="true">{{ node.nodeType === 'BOSS' ? '★' : node.orderIndex }}</div>
            <div class="challenge-node__body">
              <div class="challenge-node__heading">
                <div><p class="eyebrow">{{ CHALLENGE_NODE_LABELS[node.nodeType] }}</p><h3>{{ node.title }}</h3></div>
                <span class="challenge-node__status" :class="`challenge-node__status--${node.status}`">{{ CHALLENGE_STATUS_LABELS[node.status] }}</span>
              </div>
              <p>{{ node.description }}</p>
              <p class="field-hint">预计 {{ node.estimatedMinutes }} 分钟 · 顺序 {{ node.orderIndex }}</p>
              <p v-if="node.errorMessage" class="field-error" role="alert">{{ node.errorMessage }}</p>
              <div class="button-row">
                <button class="button-secondary button-small" type="button" :disabled="nodeLoading" @click="openNode(node)">{{ nodeActionLabel(node) }}</button>
              </div>
            </div>
            <span v-if="index < mainNodes.length - 1" class="challenge-node__connector" aria-hidden="true"></span>
          </article>
        </div>

        <div v-if="optionalNodes.length > 0" class="challenge-optional">
          <div class="challenge-map__heading">
            <div><p class="eyebrow">可选支线</p><h2>可选支线</h2></div>
            <span class="field-hint">不影响主线顺序</span>
          </div>
          <article v-for="node in optionalNodes" :key="node.id" class="challenge-node challenge-node--optional" :class="nodeStatusClass(node)">
            <div class="challenge-node__marker" aria-hidden="true">✦</div>
            <div class="challenge-node__body">
              <div class="challenge-node__heading">
                <div><p class="eyebrow">可选支线</p><h3>{{ node.title }}</h3></div>
                <span class="challenge-node__status" :class="`challenge-node__status--${node.status}`">{{ CHALLENGE_STATUS_LABELS[node.status] }}</span>
              </div>
              <p>{{ node.description }}</p>
              <p class="field-hint">预计 {{ node.estimatedMinutes }} 分钟</p>
              <button class="button-secondary button-small" type="button" :disabled="nodeLoading" @click="openNode(node)">{{ nodeActionLabel(node) }}</button>
            </div>
          </article>
        </div>
      </section>

      <section v-if="selectedNode" class="panel challenge-node-detail" aria-live="polite">
        <div class="challenge-node-detail__heading">
          <div><p class="eyebrow">节点详情</p><h2>{{ selectedNode.node.title }}</h2></div>
          <button class="link-button" type="button" @click="selectedNode = null">关闭</button>
        </div>
        <p>{{ selectedNode.node.description }}</p>
        <p class="field-hint">状态：{{ CHALLENGE_STATUS_LABELS[selectedNode.node.status] }} · 预计 {{ selectedNode.node.estimatedMinutes }} 分钟</p>
        <p v-if="selectedNode.node.status === 'locked'" class="inline-note">完成前一个节点后解锁。</p>
        <p v-else-if="readOnly" class="inline-note">跨日地图只读，不能开始或重做节点。</p>
        <p v-else-if="selectedNode.node.nodeType === 'BOSS' && selectedNode.node.status === 'completed'" class="inline-note">终点挑战已完成，可查看结果。</p>
        <ErrorNotice v-if="nodeError" :error="nodeError" :show-retry="false" />
        <div class="button-row">
          <button v-if="selectedNode.allowedActions.includes('start') || selectedNode.allowedActions.includes('resume')" class="button" type="button" :disabled="readOnly || nodeStarting" @click="startNode(selectedNode)">
            {{ nodeStarting ? '正在启动…' : (selectedNode.allowedActions.includes('resume') ? '继续节点' : '开始节点') }}
          </button>
          <button v-if="selectedNode.allowedActions.includes('view_result')" class="button-secondary" type="button" @click="viewResult(selectedNode)">查看节点结果</button>
          <RouterLink class="button-secondary" to="/overview">返回今日学习</RouterLink>
        </div>
      </section>

      <ErrorNotice v-if="planRefreshError" :error="planRefreshError" :show-retry="false" />
      <ChallengeBossPanel v-if="bossSession" :key="bossSession.sessionId" :challenge-id="plan.id" :node-id="bossSession.nodeId" :session-id="bossSession.sessionId" @completed="onBossCompleted" />

      <section id="challenge-history" class="panel challenge-history" aria-labelledby="challenge-history-title">
        <div class="challenge-map__heading">
          <div><p class="eyebrow">历史</p><h2 id="challenge-history-title">闯关历史</h2></div>
          <span class="field-hint">历史地图只读</span>
        </div>
        <LoadingState v-if="historyLoading && historyItems.length === 0" label="正在加载历史…" />
        <ErrorNotice v-else-if="historyError" :error="historyError" retry-label="重新读取历史" @retry="loadHistory(true)" />
        <div v-else-if="historyItems.length === 0" class="challenge-history__empty"><p>还没有闯关记录。</p></div>
        <ul v-else class="challenge-history__list">
          <li v-for="item in historyItems" :key="item.id">
            <RouterLink class="challenge-history__item" :to="`/challenges/${item.id}`">
              <span><strong>{{ item.localDate }} · {{ item.title || '每日闯关' }}</strong><small>{{ item.summary || '没有摘要' }}</small></span>
              <span class="challenge-history__meta"><span>{{ PLAN_STATUS_LABELS[item.status] }}</span><small>主线 {{ item.mainCompleted }} / {{ item.mainTotal }}</small></span>
            </RouterLink>
          </li>
        </ul>
        <button v-if="historyHasMore" class="button-secondary challenge-history__more" type="button" :disabled="historyLoading" @click="loadHistory(false)">{{ historyLoading ? '正在加载…' : '加载更多历史' }}</button>
      </section>
    </template>
  </article>
</template>
