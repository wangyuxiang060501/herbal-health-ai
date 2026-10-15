<template>
  <div class="page page--no-tab">
    <van-nav-bar title="体质结果" left-arrow fixed placeholder @click-left="goHome" />

    <LoadingState :loading="loading" :error="error" empty-text="结果不存在" @retry="load">
      <template v-if="data">
        <!-- 主结论 -->
        <div class="result-hero">
          <div class="badge">{{ data.constitution?.primary || '—' }}</div>
          <div class="judged">{{ data.constitution?.primary_label || '' }}</div>
          <!-- 用 v-html 会把 LLM 输出原样当 HTML 执行，这里改成按 [n] 切片渲染 -->
          <p class="interp">
            <template v-for="(seg, i) in interpParts" :key="i">
              <span v-if="seg.type === 'cite'" class="cite" @click="scrollToCite(seg.value)">
                [{{ seg.value }}]
              </span>
              <span v-else>{{ seg.value }}</span>
            </template>
          </p>
        </div>

        <!-- 兼夹体质 -->
        <div v-if="secondary.length" class="card">
          <h3 class="section-title">兼夹体质</h3>
          <div class="tag-row">
            <van-tag
              v-for="s in secondary"
              :key="s"
              type="primary"
              size="medium"
              color="#0d8050"
              plain
            >
              {{ s }}
            </van-tag>
          </div>
        </div>

        <!-- 九维雷达 -->
        <div class="card">
          <h3 class="section-title">九种体质转化分</h3>
          <div ref="radarEl" class="chart" />
          <div class="score-list">
            <div v-for="(v, k) in scores" :key="k" class="score-row">
              <span class="s-name">{{ k }}</span>
              <div class="s-bar">
                <div class="s-fill" :style="{ width: v + '%' }" :class="{ high: v >= 40, mid: v >= 30 && v < 40 }" />
              </div>
              <span class="s-val">{{ v }}</span>
              <span class="s-judge">{{ judgeOf(k) }}</span>
            </div>
          </div>
          <p class="muted">
            转化分 =（原始分 − 条目数）÷（条目数 × 4）× 100。≥40 判定「是」，30–40 判定「倾向是」。
          </p>
        </div>

        <!-- 推理依据 -->
        <div class="card">
          <h3 class="section-title">推理依据</h3>
          <div v-for="(ev, i) in evidence" :key="i" class="evidence">
            <b>{{ ev.dimension || ev.name }}</b>
            <span>{{ ev.detail || ev.text || ev }}</span>
          </div>
          <p v-if="!evidence.length" class="muted">本次判定由计分引擎直接给出，无附加证据项。</p>
        </div>

        <!-- 知识依据：RAG 引用来源（P3） -->
        <div v-if="citations.length" class="card" id="cite-panel">
          <h3 class="section-title">
            知识依据
            <span class="cite-count">{{ citations.length }} 条</span>
          </h3>
          <p class="muted cite-tip">
            以下片段由 RAG 从知识库检索后注入生成过程。解读中的 [n] 对应此处第 n 条，可逐条核对。
          </p>
          <div
            v-for="(c, i) in citations"
            :id="`cite-${i + 1}`"
            :key="c.chunk_id + i"
            class="cite-row"
            :class="{ active: activeCite === i + 1 }"
          >
            <div class="cite-head">
              <span class="cite-no">[{{ i + 1 }}]</span>
              <b>{{ c.title || c.chunk_id }}</b>
              <van-tag type="primary" size="mini" plain color="#0d8050">
                {{ sourceLabel(c.source) }}
              </van-tag>
              <span v-if="c.score" class="cite-score">{{ c.score.toFixed(4) }}</span>
            </div>
            <p class="cite-text">{{ c.text }}</p>
            <p class="cite-id">{{ c.chunk_id }}</p>
          </div>
        </div>
        <div v-else class="card">
          <h3 class="section-title">知识依据</h3>
          <p class="muted">
            本次未返回引用来源（知识库未就绪或已降级为结构化检索）。体质判定与药材推荐仍由确定性规则给出，不受影响。
          </p>
        </div>

        <!-- 推荐药材 -->
        <div class="card">
          <h3 class="section-title">推荐药材（药食同源）</h3>
          <div v-for="h in herbs" :key="h.name" class="herb-row">
            <div class="h-head">
              <b>{{ h.name }}</b>
              <span class="h-dose">{{ h.dosage || '适量' }}</span>
            </div>
            <p class="h-reason">{{ h.reason }}</p>
            <div v-if="h.contraindications?.length" class="h-warn">
              禁忌：{{ h.contraindications.join('、') }}
            </div>
          </div>
          <van-empty v-if="!herbs.length" description="本次未产出推荐" />
        </div>

        <!-- 被安全层拦截的 -->
        <div v-if="rejected.length" class="card">
          <h3 class="section-title">安全层拦截记录</h3>
          <div v-for="(r, i) in rejected" :key="i" class="rejected">
            <van-tag type="danger" size="mini">{{ r.matched || r.name }}</van-tag>
            <span>{{ r.reason || '不在药食同源目录' }}</span>
            <span v-if="r.replacement" class="rep">→ {{ r.replacement }}</span>
          </div>
          <p class="muted">以上品种已被系统拒绝或替换，不会出现在推荐方案中。</p>
        </div>

        <!-- 执行轨迹 -->
        <div class="card">
          <h3 class="section-title">多智能体执行轨迹</h3>
          <van-steps direction="vertical" :active="trace.length">
            <van-step v-for="(t, i) in trace" :key="i">
              <b>{{ t.label || t.node }}</b>
              <span class="muted">{{ t.at || '' }}</span>
            </van-step>
          </van-steps>
        </div>

        <div class="actions">
          <van-button block type="primary" color="#0d8050" @click="goRecipe">
            查看药膳方案
          </van-button>
          <van-button block plain @click="$router.push('/test')">再测一次</van-button>
        </div>

        <div class="disclaimer-bar">{{ data.disclaimer }}</div>
      </template>
    </LoadingState>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as echarts from 'echarts'
import LoadingState from '@/components/LoadingState.vue'
import { getConsultation } from '@/api'

const route = useRoute()
const router = useRouter()

const data = ref(null)
const loading = ref(true)
const error = ref('')
const radarEl = ref(null)

const scores = computed(() => data.value?.constitution?.scores || {})
const secondary = computed(() => data.value?.constitution?.secondary || [])
const evidence = computed(() => data.value?.recommend?.evidence || [])
const herbs = computed(() => data.value?.recommend?.herbs || [])
const rejected = computed(() => data.value?.recommend?.rejected || [])
const trace = computed(() => data.value?.trace || [])
const citations = computed(() => data.value?.rag_citations || [])
const activeCite = ref(0)

// 把解读里的 [n] 切成可点击的引用段，避免 v-html 直接执行 LLM 输出
const interpParts = computed(() => {
  const raw = data.value?.interpretation || ''
  const parts = []
  let last = 0
  for (const m of raw.matchAll(/\[(\d{1,2})\]/g)) {
    if (m.index > last) parts.push({ type: 'text', value: raw.slice(last, m.index) })
    parts.push({ type: 'cite', value: Number(m[1]) })
    last = m.index + m[0].length
  }
  if (last < raw.length) parts.push({ type: 'text', value: raw.slice(last) })
  return parts
})

function sourceLabel(src) {
  return (
    {
      food_medicine: '药食同源目录',
      herb: '药材知识库',
      constitution: '体质标准',
      symptom: '症状映射',
      safety: '安全规则'
    }[src] || src || '知识库'
  )
}

function scrollToCite(n) {
  activeCite.value = n
  nextTick(() => {
    const el = document.getElementById(`cite-${n}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      setTimeout(() => (activeCite.value = 0), 1600)
    }
  })
}

function judgeOf(k) {
  return data.value?.constitution?.details?.[k]?.judged || ''
}

onMounted(load)

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await getConsultation(route.params.id)
    await nextTick()
    drawRadar()
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function drawRadar() {
  if (!radarEl.value || !Object.keys(scores.value).length) return
  const keys = Object.keys(scores.value)
  const chart = echarts.init(radarEl.value)
  chart.setOption({
    radar: {
      indicator: keys.map((k) => ({ name: k, max: 100 })),
      radius: '62%',
      axisName: { fontSize: 10, color: '#6b7280' },
      splitArea: { areaStyle: { color: ['#fbfdfc', '#f2f7f4'] } }
    },
    series: [
      {
        type: 'radar',
        data: [
          {
            value: keys.map((k) => scores.value[k]),
            name: '转化分',
            areaStyle: { color: 'rgba(13,128,80,0.22)' },
            lineStyle: { color: '#0d8050' },
            itemStyle: { color: '#0d8050' }
          }
        ]
      }
    ]
  })
  window.addEventListener('resize', () => chart.resize())
}

function goRecipe() {
  router.push(`/recipe/${route.params.id}`)
}
function goHome() {
  router.push('/')
}
</script>

<style scoped>
.result-hero {
  background: linear-gradient(135deg, #0d8050, #15a06a);
  color: #fff;
  padding: 46px 16px 18px;
  text-align: center;
}
.badge {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: 2px;
}
.judged {
  font-size: 12px;
  opacity: 0.9;
  margin-top: 2px;
}
.interp {
  margin: 10px 0 0;
  font-size: 12.5px;
  line-height: 1.75;
  opacity: 0.95;
  text-align: left;
  white-space: pre-wrap;
}
.chart {
  width: 100%;
  height: 260px;
}
.score-list {
  margin-top: 6px;
}
.score-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
  font-size: 11.5px;
}
.s-name {
  width: 48px;
  color: var(--c-text-sub);
}
.s-bar {
  flex: 1;
  height: 6px;
  background: #eef1ee;
  border-radius: 3px;
  overflow: hidden;
}
.s-fill {
  height: 100%;
  background: #b9cfc3;
}
.s-fill.mid {
  background: #e6a23c;
}
.s-fill.high {
  background: #d9534f;
}
.s-val {
  width: 28px;
  text-align: right;
}
.s-judge {
  width: 46px;
  color: var(--c-text-sub);
}
.evidence {
  padding: 6px 0;
  border-bottom: 1px dashed var(--c-border);
  font-size: 12.5px;
  line-height: 1.7;
}
.evidence b {
  color: var(--c-primary);
  margin-right: 6px;
}
.herb-row {
  padding: 8px 0;
  border-bottom: 1px dashed var(--c-border);
}
.h-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.h-head b {
  font-size: 14.5px;
}
.h-dose {
  font-size: 11.5px;
  color: var(--c-text-sub);
}
.h-reason {
  margin: 4px 0 0;
  font-size: 12px;
  color: #3f4752;
  line-height: 1.65;
}
.h-warn {
  margin-top: 3px;
  font-size: 11px;
  color: #c0392b;
}
.rejected {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  padding: 4px 0;
}
.rep {
  color: var(--c-primary);
}
.cite-count {
  margin-left: 6px;
  font-size: 11px;
  font-weight: 400;
  color: var(--c-text-sub);
}
.cite-tip {
  margin: -2px 0 8px;
  font-size: 11.5px;
  line-height: 1.6;
}
.cite {
  display: inline-block;
  margin: 0 1px;
  padding: 0 3px;
  font-size: 10.5px;
  color: #0d8050;
  background: rgba(13, 128, 80, 0.1);
  border-radius: 3px;
  vertical-align: super;
  cursor: pointer;
}
.cite-row {
  padding: 8px 10px;
  margin-bottom: 6px;
  border-left: 3px solid #d9e6de;
  background: #fafcfb;
  border-radius: 0 6px 6px 0;
  transition: background 0.2s, border-color 0.2s;
}
.cite-row.active {
  border-left-color: #0d8050;
  background: rgba(13, 128, 80, 0.08);
}
.cite-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 12.5px;
}
.cite-no {
  color: #0d8050;
  font-weight: 600;
}
.cite-score {
  margin-left: auto;
  font-size: 10.5px;
  color: var(--c-text-sub);
}
.cite-text {
  margin: 5px 0 0;
  font-size: 11.5px;
  line-height: 1.7;
  color: #3f4752;
}
.cite-id {
  margin: 3px 0 0;
  font-size: 10px;
  color: #9aa4ad;
  word-break: break-all;
}
.actions {
  padding: 12px 16px 24px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>
