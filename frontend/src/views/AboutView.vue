<template>
  <div class="page page--no-tab">
    <van-nav-bar title="关于本系统" left-arrow fixed placeholder @click-left="$router.back()" />

    <van-tabs v-model:active="tab" color="#0d8050" sticky offset-top="46px">
      <!-- 说明 -->
      <van-tab title="说明">
        <div class="card">
          <h3 class="section-title">这是什么</h3>
          <p class="body-text">
            基于多智能体协同与检索增强生成的中医药智慧康养系统。
            通过标准化体质问卷判定中医体质倾向，结合国家药食同源目录推荐日常食疗方向，
            全程由安全合规层把关，不提供疾病诊断与用药指导。
          </p>
        </div>

        <div class="card">
          <h3 class="section-title">免责声明</h3>
          <ol class="disc">
            <li>本系统不属于医疗诊断，不能替代执业医师诊疗。</li>
            <li>出现胸痛、呼吸困难、持续高热、意识障碍、大出血等，请立即就医或拨打 120。</li>
            <li>推荐药材仅限国家药食同源目录内品种。</li>
            <li>孕妇、哺乳期、儿童、慢性病患者及正在服药者请先咨询医师或药师。</li>
            <li>食用后如有不适，请立即停止并就医。</li>
          </ol>
        </div>

        <div class="card">
          <h3 class="section-title">数据集</h3>
          <van-cell-group inset>
            <van-cell title="药材条目（去重后）" :value="String(dataset.unique || '—')" />
            <van-cell title="原始记录条数" :value="String(dataset.raw || '—')" />
            <van-cell title="药食同源白名单" :value="String(dataset.whitelist || '—')" />
            <van-cell title="黑名单品种" :value="String(dataset.blacklist || '—')" />
          </van-cell-group>
          <p class="muted">
            「828」是原始记录条数而非品种数——去重合并后唯一药材为 604 味，
            另有 22 味法定可食用品种由白名单补齐。论文与答辩中请勿把 828 当作品种数。
          </p>
        </div>

        <div class="card">
          <h3 class="section-title">运行配置</h3>
          <van-cell-group inset>
            <van-cell title="LLM 提供方" :value="config.llm_provider || '—'" />
            <van-cell title="默认模型" :value="config.llm_model || '—'" />
            <van-cell title="安全层" value="三道闸：急症 / 白名单 / 输出过滤" />
            <van-cell title="判定标准" value="GB/T 46939—2025 等级计分" />
          </van-cell-group>
        </div>
      </van-tab>

      <!-- 状态图 -->
      <van-tab title="状态图">
        <div class="card">
          <h3 class="section-title">问诊状态图（LangGraph）</h3>
          <p class="muted">
            下图由后端 <code>GET /api/v1/consultation/graph</code> 实时导出，
            与线上执行的图是同一份定义。
          </p>
          <div v-for="n in nodes" :key="n.name" class="node-row">
            <van-tag :type="n.kind === 'llm' ? 'primary' : 'default'" size="mini">
              {{ n.kind === 'llm' ? 'LLM' : '规则' }}
            </van-tag>
            <b>{{ n.name }}</b>
            <span>{{ n.label }}</span>
          </div>
          <van-button
            class="fold-btn"
            size="small"
            plain
            block
            @click="showSrc = !showSrc"
          >
            {{ showSrc ? '收起 mermaid 源码' : '展开 mermaid 源码' }}
          </van-button>
          <pre v-if="showSrc" class="src">{{ mermaid }}</pre>
        </div>
      </van-tab>

      <!-- 安全规则 -->
      <van-tab title="安全规则">
        <div class="card">
          <h3 class="section-title">三道安全闸</h3>
          <div class="gate">
            <b>① 输入侧急症拦截</b>
            <p>命中胸痛、呼吸困难、意识障碍等关键词 → 立即终止问诊并引导就医。</p>
          </div>
          <div class="gate">
            <b>② 推荐侧白名单硬校验</b>
            <p>推荐药材必须全部在国家药食同源目录内；高危药材拒绝或替换为安全品种。</p>
          </div>
          <div class="gate">
            <b>③ 输出侧术语过滤</b>
            <p>LLM 生成的自由文本中若出现「主治」「治愈」「服用剂量」等医疗术语，会被改写或剔除。</p>
          </div>
        </div>

        <div class="card">
          <h3 class="section-title">高危药材（示例）</h3>
          <div class="tag-row">
            <van-tag v-for="h in blacklist" :key="h" type="danger" size="medium">{{ h }}</van-tag>
          </div>
          <p class="muted">这些品种可查询百科信息，但永远不会进入任何推荐方案。</p>
        </div>
      </van-tab>
    </van-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getConfig, getDataset, getGraph, getSafetyRules } from '@/api'

const route = useRoute()
const tab = ref(0)
const dataset = ref({})
const config = ref({})
const rules = ref({})
const graph = ref(null)
const showSrc = ref(false)

const nodes = computed(() => graph.value?.nodes || [])
const mermaid = computed(() => graph.value?.mermaid || '')
const blacklist = computed(() => {
  const b = rules.value?.blacklist || rules.value?.blacklist_herbs || []
  return Array.isArray(b) ? b.slice(0, 30) : []
})

onMounted(async () => {
  if (route.query.tab === 'graph') tab.value = 1
  try {
    const [d, c, r] = await Promise.all([getDataset(), getConfig(), getSafetyRules()])
    dataset.value = {
      unique: d.query_layer?.unique_herbs,
      raw: d.query_layer?.raw_records,
      whitelist: d.whitelist_layer?.count,
      blacklist: d.query_layer?.blacklist_count
    }
    config.value = c
    rules.value = r
  } catch {
    /* 忽略 */
  }
})

watch(tab, async (v) => {
  if (v === 1 && !graph.value) {
    try {
      graph.value = await getGraph('json')
    } catch {
      /* 忽略 */
    }
  }
})
</script>

<style scoped>
.body-text {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.8;
  color: #3f4752;
}
.disc {
  padding-left: 18px;
  margin: 0;
  font-size: 12.5px;
  line-height: 1.8;
  color: #3f4752;
}
.node-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 0;
  font-size: 12.5px;
  border-bottom: 1px dashed var(--c-border);
}
.node-row b {
  min-width: 108px;
}
.node-row span {
  color: var(--c-text-sub);
}
.fold-btn {
  margin-top: 10px;
}
.src {
  background: #f5f7f5;
  border-radius: 8px;
  padding: 10px;
  font-size: 11px;
  overflow-x: auto;
  white-space: pre;
  line-height: 1.6;
}
.gate {
  padding: 8px 0;
  border-bottom: 1px dashed var(--c-border);
}
.gate b {
  font-size: 13.5px;
  color: var(--c-primary);
}
.gate p {
  margin: 3px 0 0;
  font-size: 12.5px;
  color: #3f4752;
  line-height: 1.7;
}
</style>
