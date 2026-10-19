<template>
  <div class="page page--no-tab">
    <van-nav-bar title="药膳方案" left-arrow fixed placeholder @click-left="$router.back()" />

    <LoadingState :loading="loading" :error="error" @retry="load">
      <template v-if="data">
        <div class="recipe-hero">
          <span class="tag">{{ data.constitution?.primary || '—' }}调理</span>
          <h2>{{ data.constitution?.primary || '' }}食疗建议</h2>
          <p class="muted">{{ data.constitution?.primary_label || '' }}</p>
        </div>

        <!-- Agent3 生成的药膳（P3 开关） -->
        <div v-if="recipe" class="card">
          <h3 class="section-title">AI 药膳方案</h3>
          <div class="recipe-body">{{ recipe }}</div>
        </div>

        <div v-else class="card">
          <h3 class="section-title">AI 药膳方案</h3>
          <van-empty description="药膳生成节点（Agent3）当前未启用">
            <p class="muted">
              该节点由后端 <code>enable_recipe</code> 开关控制，属 RAG 阶段（P3）能力。
              下方按推荐药材给出代茶饮与食疗方向。
            </p>
          </van-empty>
        </div>

        <!-- 可保存为图片的药膳卡片（清单 5.2.3 / 5.6.4） -->
        <div class="card">
          <h3 class="section-title">药膳卡片</h3>
          <RecipeCard
            :constitution="data.constitution?.primary || '平和'"
            :herbs="herbs"
            :recipe="recipe"
            :cautions="cautions"
          />
        </div>

        <!-- 代茶饮：完全由推荐药材派生，不新增药材 -->
        <div class="card">
          <h3 class="section-title">代茶饮组合</h3>
          <div v-for="h in herbs" :key="h.name" class="tea-row">
            <van-icon name="hotel-o" color="#0d8050" />
            <div>
              <b>{{ h.name }}</b>
              <span class="dose">{{ h.dosage || '3–5g' }}</span>
              <p>{{ h.reason }}</p>
            </div>
          </div>
          <van-empty v-if="!herbs.length" description="暂无可用药材" />
          <div class="tea-tip">
            <b>做法：</b>取上述药材，沸水冲泡或加水 500ml 小火煮 15 分钟，温服，每日 1 剂。
          </div>
        </div>

        <!-- 配伍禁忌 -->
        <div class="card">
          <h3 class="section-title">配伍与人群禁忌</h3>
          <div v-for="(r, i) in cautions" :key="i" class="caution">
            <van-icon name="warning-o" color="#e6a23c" size="13" />
            <span>{{ r }}</span>
          </div>
          <van-empty v-if="!cautions.length" description="本次推荐未触发禁忌项" />
        </div>

        <!-- 安全裁决 -->
        <div class="card">
          <h3 class="section-title">安全校验</h3>
          <van-cell-group inset>
            <van-cell title="推荐品种数" :value="String(herbs.length)" />
            <van-cell title="药食同源校验" :value="crossChecked ? '已通过' : '未执行'" />
            <van-cell title="拦截品种" :value="String(rejected.length)" />
          </van-cell-group>
          <div v-for="(r, i) in rejected" :key="i" class="rejected">
            <van-tag type="danger" size="mini">{{ r.matched || r.name }}</van-tag>
            <span>{{ r.reason }}</span>
            <span v-if="r.replacement" class="rep">→ {{ r.replacement }}</span>
          </div>
        </div>

        <div class="disclaimer-bar">{{ data.disclaimer }}</div>
      </template>
    </LoadingState>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import LoadingState from '@/components/LoadingState.vue'
import RecipeCard from '@/components/RecipeCard.vue'
import { getConsultation } from '@/api'

const route = useRoute()
const data = ref(null)
const loading = ref(true)
const error = ref('')

const recipe = computed(() => {
  const r = data.value?.recipe
  if (!r) return ''
  if (typeof r === 'string') return r
  // 后端 recipe 结构：{plan: "JSON+免责文本", source: "...", enabled: true}
  const plan = r.plan || r.text || r.content || ''
  // 去掉 LLM 可能输出的 markdown 代码块包裹
  const cleaned = plan.replace(/^```(?:json)?\s*\n?/i, '').replace(/\n?```\s*$/i, '').trim()
  if (typeof cleaned === 'string' && cleaned.startsWith('{')) {
    // 提取 JSON 部分（LLM 输出可能在 JSON 后拼接免责文本）
    let jsonEnd = 0
    let depth = 0
    for (let i = 0; i < cleaned.length; i++) {
      if (cleaned[i] === '{') depth++
      else if (cleaned[i] === '}') { depth--; if (depth === 0) { jsonEnd = i + 1; break } }
    }
    const jsonPart = jsonEnd > 0 ? cleaned.slice(0, jsonEnd) : cleaned
    const tail = jsonEnd > 0 ? cleaned.slice(jsonEnd).trim() : ''
    try {
      const parsed = JSON.parse(jsonPart)
      const recipes = parsed.recipes || []
      const result = recipes.map((rc) => {
        const parts = [`【${rc.name}】（${rc.type || '药膳'}）`]
        if (rc.fit_constitution) parts.push(`适宜体质：${rc.fit_constitution}`)
        if (rc.ingredients?.length) {
          parts.push('用料：' + rc.ingredients.map(i => `${i.name} ${i.amount || ''}`).join('、'))
        }
        if (rc.steps?.length) {
          parts.push('做法：\n' + rc.steps.map((s, i) => `${i + 1}. ${s}`).join('\n'))
        }
        if (rc.caution?.length) parts.push('禁忌：' + rc.caution.join('；'))
        if (rc.cycle_notice) parts.push('疗程：' + rc.cycle_notice)
        return parts.join('\n')
      }).join('\n\n')
      return tail ? result + '\n\n' + tail : result
    } catch { return plan }
  }
  return plan
})
const herbs = computed(() => data.value?.recommend?.herbs || [])
const rejected = computed(() => data.value?.recommend?.rejected || [])
const crossChecked = computed(() => !!data.value?.recommend?.cross_checked)

const cautions = computed(() => {
  const out = []
  for (const h of herbs.value) {
    for (const c of h.contraindications || []) {
      if (!out.includes(`${h.name}：${c}`)) out.push(`${h.name}：${c}`)
    }
    for (const g of h.special_groups || []) {
      if (!out.includes(`${h.name}：${g}慎用`)) out.push(`${h.name}：${g}慎用`)
    }
  }
  if (data.value?.special_groups?.length) {
    out.push(`本次已标记人群：${data.value.special_groups.join('、')}`)
  }
  return out
})

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
</script>

<style scoped>
.recipe-hero {
  padding: 60px 16px 12px;
}
.recipe-hero h2 {
  margin: 6px 0 2px;
  font-size: 19px;
}
.tag {
  background: var(--c-primary-light);
  color: var(--c-primary);
  font-size: 11px;
  border-radius: 10px;
  padding: 2px 8px;
}
.recipe-body {
  font-size: 13.5px;
  line-height: 1.85;
  white-space: pre-wrap;
  color: #3f4752;
}
.tea-row {
  display: flex;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px dashed var(--c-border);
}
.tea-row b {
  font-size: 14px;
}
.tea-row .dose {
  font-size: 11.5px;
  color: var(--c-text-sub);
  margin-left: 6px;
}
.tea-row p {
  margin: 3px 0 0;
  font-size: 12px;
  color: #3f4752;
  line-height: 1.6;
}
.tea-tip {
  margin-top: 10px;
  font-size: 12px;
  background: #f5f7f5;
  border-radius: 8px;
  padding: 8px 10px;
  line-height: 1.7;
  color: #3f4752;
}
.caution {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 12.5px;
  padding: 4px 0;
  color: #3f4752;
}
.rejected {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  padding: 3px 0;
}
.rep {
  color: var(--c-primary);
}
</style>
