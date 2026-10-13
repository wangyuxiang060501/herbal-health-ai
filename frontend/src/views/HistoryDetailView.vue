<template>
  <div class="page page--no-tab">
    <van-nav-bar title="问诊记录" left-arrow fixed placeholder @click-left="$router.back()" />

    <LoadingState :loading="loading" :error="error" empty-text="记录不存在" @retry="load">
      <template v-if="data">
        <div class="card">
          <h3 class="section-title">主诉</h3>
          <p class="body-text">{{ data.chief_complaint || '—' }}</p>
          <p class="muted">记录号 {{ data.id }} · {{ fmtTime(data.created_at) }}</p>
        </div>

        <div v-if="data.constitution" class="card">
          <h3 class="section-title">体质判定</h3>
          <div class="tag-row">
            <van-tag type="success" size="medium" color="#0d8050">
              {{ data.constitution.primary }}
            </van-tag>
            <van-tag
              v-for="s in data.constitution.secondary || []"
              :key="s"
              plain
              size="medium"
            >
              {{ s }}
            </van-tag>
          </div>
        </div>

        <div v-if="herbs.length" class="card">
          <h3 class="section-title">推荐药材</h3>
          <div class="tag-row">
            <van-tag v-for="h in herbs" :key="h.name" type="primary" size="medium" color="#0d8050">
              {{ h.name }}
            </van-tag>
          </div>
        </div>

        <div class="card">
          <h3 class="section-title">对话过程</h3>
          <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
            <span class="role">{{ roleText(m.role) }}</span>
            <span class="content">{{ m.content }}</span>
          </div>
          <van-empty v-if="!messages.length" description="无对话记录" />
        </div>

        <div v-if="data.status === 'blocked_emergency'" class="disclaimer-bar danger">
          本次问诊因急症关键词被系统终止，已建议立即就医。
        </div>
        <div class="disclaimer-bar">{{ data.disclaimer }}</div>

        <div class="actions">
          <van-button block type="primary" color="#0d8050" @click="goRecipe">查看药膳方案</van-button>
        </div>
      </template>
    </LoadingState>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import LoadingState from '@/components/LoadingState.vue'
import { getConsultation } from '@/api'

const route = useRoute()
const router = useRouter()
const data = ref(null)
const loading = ref(true)
const error = ref('')

const messages = computed(() => data.value?.messages || [])
const herbs = computed(() => data.value?.recommend?.herbs || [])

const roleText = { user: '我', ai: '系统', system: '系统' }

onMounted(load)
async function load() {
  loading.value = true
  try {
    data.value = await getConsultation(route.params.id)
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function fmtTime(t) {
  return t ? String(t).replace('T', ' ').slice(0, 16) : ''
}
function goRecipe() {
  router.push(`/recipe/${route.params.id}`)
}
</script>

<style scoped>
.body-text {
  margin: 0 0 6px;
  font-size: 13.5px;
  line-height: 1.75;
}
.msg {
  display: flex;
  gap: 8px;
  padding: 6px 0;
  font-size: 13px;
  line-height: 1.7;
}
.msg .role {
  flex-shrink: 0;
  color: var(--c-primary);
  font-weight: 600;
}
.msg.ai .role {
  color: var(--c-text-sub);
}
.disclaimer-bar.danger {
  background: #fdecea;
  border-color: #f5c6c0;
  color: #b03026;
}
.actions {
  padding: 12px 16px 24px;
}
</style>
