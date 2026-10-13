<template>
  <div class="page">
    <div class="mine-hero">
      <div class="avatar" @click="goLogin">
        <van-icon name="user-o" size="26" color="#fff" />
      </div>
      <div class="who">
        <b>{{ user.displayName }}</b>
        <span>{{ user.isLogin ? user.phone : '点击头像设置身份（本地）' }}</span>
      </div>
      <van-icon v-if="user.isLogin" name="setting-o" size="18" @click="onLogout" />
    </div>

    <div class="card">
      <h3 class="section-title">体质变化趋势</h3>
      <div v-if="trend.length" ref="trendEl" class="chart" />
      <van-empty v-else description="还没有记录，先做一次体质测试" />
    </div>

    <div class="card">
      <h3 class="section-title">问诊记录</h3>
      <LoadingState :loading="loading" :error="error" :empty="!history.length" empty-text="暂无问诊记录" @retry="load">
        <div
          v-for="item in history"
          :key="item.id"
          class="hist-row"
          @click="$router.push(`/history/${item.id}`)"
        >
          <div class="h-left">
            <b>{{ item.primary || '未判定' }}</b>
            <span class="muted">{{ fmtTime(item.created_at || item.date) }}</span>
          </div>
          <div class="h-right">
            <span class="chief">{{ item.chief_complaint || '—' }}</span>
            <van-icon name="arrow" color="#c8c9cc" />
          </div>
        </div>
      </LoadingState>
    </div>

    <div class="card">
      <h3 class="section-title">其他</h3>
      <van-cell-group inset>
        <van-cell title="关于与免责声明" is-link to="/about" />
        <van-cell title="查看问诊状态图" is-link to="/about?tab=graph" />
        <van-cell title="重置免责声明确认" is-link @click="resetDisclaimer" />
      </van-cell-group>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'
import * as echarts from 'echarts'
import LoadingState from '@/components/LoadingState.vue'
import { getHistory, getTrend } from '@/api'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const user = useUserStore()

const history = ref([])
const trend = ref([])
const loading = ref(true)
const error = ref('')
const trendEl = ref(null)

onMounted(load)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [h, t] = await Promise.all([getHistory(20), getTrend(20)])
    history.value = Array.isArray(h) ? h : h?.items || []
    trend.value = Array.isArray(t) ? t : []
    await nextTick()
    drawTrend()
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function drawTrend() {
  if (!trendEl.value || !trend.value.length) return
  // 后端返回按时间倒序，这里正序展示
  const rows = [...trend.value].reverse()
  const chart = echarts.init(trendEl.value)
  chart.setOption({
    grid: { left: 34, right: 12, top: 18, bottom: 30 },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: rows.map((r) => (r.date || '').slice(5)),
      axisLabel: { fontSize: 10, color: '#6b7280' }
    },
    yAxis: {
      type: 'category',
      data: ['平和质', '气虚质', '阳虚质', '阴虚质', '痰湿质', '湿热质', '血瘀质', '气郁质', '特禀质'],
      axisLabel: { fontSize: 9, color: '#6b7280' }
    },
    series: [
      {
        type: 'line',
        step: 'end',
        symbolSize: 8,
        data: rows.map((r) => r.primary),
        lineStyle: { color: '#0d8050', width: 2 },
        itemStyle: { color: '#0d8050' }
      }
    ]
  })
  window.addEventListener('resize', () => chart.resize())
}

function fmtTime(t) {
  if (!t) return ''
  return String(t).replace('T', ' ').slice(0, 16)
}

function goLogin() {
  router.push('/login')
}

async function onLogout() {
  try {
    await showConfirmDialog({ title: '退出', message: '将清除本地身份信息（问诊记录不受影响）' })
    user.logout()
    showToast('已退出')
  } catch {
    /* 取消 */
  }
}

function resetDisclaimer() {
  user.resetDisclaimer()
  showToast('下次进入将重新确认')
}
</script>

<style scoped>
.mine-hero {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 22px 16px 16px;
  background: linear-gradient(135deg, #0d8050, #15a06a);
  color: #fff;
}
.avatar {
  width: 48px;
  height: 48px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.22);
  display: flex;
  align-items: center;
  justify-content: center;
}
.who b {
  display: block;
  font-size: 16px;
}
.who span {
  font-size: 11.5px;
  opacity: 0.85;
}
.chart {
  width: 100%;
  height: 240px;
}
.hist-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-bottom: 1px dashed var(--c-border);
}
.h-left b {
  font-size: 14px;
}
.h-left span {
  display: block;
}
.h-right {
  display: flex;
  align-items: center;
  gap: 4px;
  max-width: 55%;
}
.chief {
  font-size: 11.5px;
  color: var(--c-text-sub);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
