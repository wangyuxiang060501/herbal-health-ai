<template>
  <div class="page">
    <div class="hero">
      <div class="hero-inner">
        <div class="hello">
          <span class="hi">{{ greeting }}，{{ user.displayName }}</span>
          <span class="sub">药食同源 · 中医体质智慧康养</span>
        </div>
        <van-image
          round
          width="44"
          height="44"
          src="data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='44' height='44'><rect width='44' height='44' rx='22' fill='%23ffffff' opacity='0.25'/><text x='22' y='29' font-size='20' text-anchor='middle' fill='%23fff'>药</text></svg>"
        />
      </div>

      <div class="stats">
        <div class="stat" @click="$router.push('/herbs')">
          <b>{{ dataset.unique || '—' }}</b>
          <span>药材条目</span>
        </div>
        <div class="stat">
          <b>{{ dataset.whitelist || '—' }}</b>
          <span>药食同源</span>
        </div>
        <div class="stat">
          <b>9</b>
          <span>体质分型</span>
        </div>
      </div>
    </div>

    <div class="entries">
      <div class="entry big" @click="goTest">
        <van-icon name="records" size="22" />
        <div>
          <b>体质测试</b>
          <span>27 题 · 标准计分 · AI 追问</span>
        </div>
      </div>
      <div class="entry" @click="$router.push('/herbs')">
        <van-icon name="flower-o" size="20" />
        <div>
          <b>药材库</b>
          <span>查功效归经</span>
        </div>
      </div>
      <div class="entry" @click="goLastRecipe">
        <van-icon name="hotel-o" size="20" />
        <div>
          <b>药膳推荐</b>
          <span>{{ consult.lastConsultationId ? '查看上一次' : '先做测试' }}</span>
        </div>
      </div>
    </div>

    <div class="card">
      <h3 class="section-title">九种体质</h3>
      <div class="const-grid">
        <div
          v-for="(info, name) in constitutions"
          :key="name"
          class="const-item"
          @click="$router.push('/test')"
        >
          <b>{{ name }}</b>
          <span>{{ info.desc }}</span>
        </div>
      </div>
    </div>

    <div class="card">
      <h3 class="section-title">系统状态</h3>
      <van-cell-group inset>
        <van-cell title="LLM 提供方" :value="llmText" />
        <van-cell title="体质判定" value="GB/T 46939—2025 确定性计分" />
        <van-cell title="推荐范围" value="仅限国家药食同源目录" is-link to="/about" />
      </van-cell-group>
    </div>

    <div class="disclaimer-bar">
      本系统仅提供中医体质倾向参考与日常食疗方向建议，不属于医疗诊断，不能替代执业医师诊疗。
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import { getConstitutions, getDataset, getLlmStatus } from '@/api'
import { useUserStore } from '@/stores/user'
import { useConsultStore } from '@/stores/consult'

const router = useRouter()
const user = useUserStore()
const consult = useConsultStore()

const dataset = ref({})
const constitutions = ref({})
const llm = ref({})

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 11) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

const llmText = computed(() => {
  if (!llm.value || !llm.value.provider) return '加载中…'
  return `${llm.value.provider}${llm.value.model ? ' · ' + llm.value.model : ''}`
})

const datasetUnique = computed(() => dataset.value?.query_layer?.unique_herbs)

onMounted(async () => {
  try {
    const [d, c, l] = await Promise.all([getDataset(), getConstitutions(), getLlmStatus()])
    dataset.value = {
      unique: d.query_layer?.unique_herbs ?? d.total_herbs ?? '—',
      whitelist: d.whitelist_layer?.count ?? '—'
    }
    constitutions.value = c
    llm.value = l
  } catch {
    /* 后端未启动时首页仍可渲染 */
  }
})

function goTest() {
  router.push('/test')
}

function goLastRecipe() {
  if (consult.lastConsultationId) router.push(`/recipe/${consult.lastConsultationId}`)
  else showToast('请先完成一次体质测试')
}
</script>

<style scoped>
.hero {
  background: linear-gradient(135deg, #0d8050, #15a06a);
  color: #fff;
  padding: 18px 16px 22px;
  border-bottom-left-radius: 18px;
  border-bottom-right-radius: 18px;
}
.hero-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.hi {
  display: block;
  font-size: 17px;
  font-weight: 600;
}
.sub {
  display: block;
  font-size: 12px;
  opacity: 0.85;
  margin-top: 2px;
}
.stats {
  display: flex;
  margin-top: 16px;
  background: rgba(255, 255, 255, 0.16);
  border-radius: 12px;
  padding: 10px 0;
}
.stat {
  flex: 1;
  text-align: center;
}
.stat b {
  display: block;
  font-size: 19px;
}
.stat span {
  font-size: 11px;
  opacity: 0.85;
}
.entries {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin: 12px;
}
.entry {
  background: #fff;
  border-radius: 12px;
  padding: 14px;
  display: flex;
  align-items: center;
  gap: 10px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}
.entry b {
  display: block;
  font-size: 14px;
}
.entry span {
  font-size: 11px;
  color: var(--c-text-sub);
}
.entry.big {
  grid-column: span 2;
  background: linear-gradient(120deg, #eaf6f0, #ffffff);
  border: 1px solid #d6ecdf;
}
.const-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.const-item {
  background: #f5f7f5;
  border-radius: 8px;
  padding: 8px 6px;
  text-align: center;
}
.const-item b {
  display: block;
  font-size: 12.5px;
  color: var(--c-primary);
}
.const-item span {
  display: block;
  font-size: 10px;
  color: var(--c-text-sub);
  line-height: 1.4;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
</style>
