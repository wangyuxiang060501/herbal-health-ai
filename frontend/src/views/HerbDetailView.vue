<template>
  <div class="page page--no-tab">
    <van-nav-bar title="药材详情" left-arrow fixed placeholder @click-left="$router.back()" />

    <LoadingState :loading="loading" :error="error" empty-text="药材不存在" @retry="load">
      <template v-if="herb">
        <div class="detail-head">
          <h2>{{ herb.name }}</h2>
          <div class="tags">
            <van-tag v-if="herb.is_blacklisted" type="danger" size="medium">高危药材</van-tag>
            <van-tag v-else-if="herb.is_food_medicine" type="success" size="medium" color="#0d8050">
              药食同源
            </van-tag>
            <van-tag v-else plain size="medium">仅供知识查询</van-tag>
            <van-tag v-if="herb.has_conflict" type="warning" size="medium">数据存在冲突</van-tag>
          </div>
        </div>

        <div class="card">
          <h3 class="section-title">基本信息</h3>
          <van-cell-group inset>
            <van-cell title="分类" :value="herb.category || '—'" />
            <van-cell title="归经" :value="herb.meridian || '—'" />
            <van-cell title="常用量" :value="herb.dosage || '—'" />
            <van-cell v-if="herb.merged_from > 1" title="数据合并" :value="`由 ${herb.merged_from} 条重复记录合并`" />
          </van-cell-group>
        </div>

        <div class="card">
          <h3 class="section-title">功效</h3>
          <p class="body-text">{{ herb.effect || '—' }}</p>
        </div>

        <div class="card">
          <h3 class="section-title">主要成分</h3>
          <p class="body-text">{{ herb.component || '—' }}</p>
        </div>

        <!-- 安全裁决：直接调用后端 /safety/probe-herbs，不由前端判断 -->
        <div class="card">
          <h3 class="section-title">使用范围裁决</h3>
          <div v-if="verdict" class="verdict" :class="{ pass: verdict.passed, fail: !verdict.passed }">
            <van-icon :name="verdict.passed ? 'passed' : 'warning-o'" size="16" />
            <span>{{ verdict.passed ? '允许进入药膳方案' : '不得进入药膳方案' }}</span>
          </div>
          <div v-if="verdict && verdict.verdict?.triggers?.length" class="triggers">
            <div v-for="(t, i) in verdict.verdict.triggers" :key="i" class="trigger">
              <van-tag :type="t.action === 'reject' ? 'danger' : 'warning'">
                {{ actionText[t.action] || t.action }}
              </van-tag>
              <span>{{ t.matched }} —— {{ t.detail || t.reason }}</span>
              <span v-if="t.replacement" class="rep">替换为：{{ t.replacement }}</span>
            </div>
          </div>
          <p v-else-if="verdict" class="muted">未触发任何安全规则。</p>
        </div>

        <div class="disclaimer-bar">{{ herb.usage_policy }}</div>
        <div class="disclaimer-bar muted">{{ herb.source_note }}</div>
      </template>
    </LoadingState>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import LoadingState from '@/components/LoadingState.vue'
import { getHerb, probeHerbs } from '@/api'

const route = useRoute()
const herb = ref(null)
const verdict = ref(null)
const loading = ref(true)
const error = ref('')

const actionText = { reject: '拒绝', replace: '替换', warn: '警示' }

onMounted(load)

async function load() {
  loading.value = true
  error.value = ''
  try {
    herb.value = await getHerb(route.params.id)
    // 安全裁决总是调用一次，让用户看到"系统确实拦得住"
    try {
      verdict.value = await probeHerbs([herb.value.name])
    } catch {
      verdict.value = null
    }
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.detail-head {
  padding: 16px 16px 6px;
}
.detail-head h2 {
  margin: 0 0 8px;
  font-size: 22px;
}
.tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.body-text {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.8;
  color: #3f4752;
}
.verdict {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 13px;
}
.verdict.pass {
  background: #eaf6ee;
  color: #0d5c39;
}
.verdict.fail {
  background: #fdecea;
  color: #b03026;
}
.triggers {
  margin-top: 8px;
}
.trigger {
  font-size: 12px;
  line-height: 1.7;
  padding: 4px 0;
  color: #3f4752;
}
.rep {
  color: var(--c-primary);
}
</style>
