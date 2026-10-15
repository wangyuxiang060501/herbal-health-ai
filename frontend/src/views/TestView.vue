<template>
  <div class="page page--no-tab">
    <van-nav-bar title="体质测试" left-arrow fixed placeholder @click-left="$router.back()" />

    <!-- 步骤 1：主诉 -->
    <div v-if="step === 0" class="step">
      <div class="card">
        <h3 class="section-title">先说说你的情况</h3>
        <van-field
          v-model="chief"
          type="textarea"
          rows="4"
          maxlength="200"
          show-word-limit
          placeholder="例如：最近总是怕冷、手脚冰凉，稍微活动就觉得累…"
        />
        <p class="muted">
          这段话会先经过急症关键词筛查。若出现胸痛、呼吸困难等急症表现，系统会立即停止并提示就医。
        </p>
      </div>

      <div class="card">
        <h3 class="section-title">特殊人群（可多选）</h3>
        <div class="tag-row">
          <van-tag
            v-for="g in GROUP_OPTIONS"
            :key="g"
            :type="groups.includes(g) ? 'success' : 'default'"
            :color="groups.includes(g) ? '#0d8050' : ''"
            size="medium"
            @click="toggleGroup(g)"
          >
            {{ g }}
          </van-tag>
        </div>
        <p class="muted">勾选后，推荐时会额外做人群禁忌校验。</p>
      </div>

      <div class="card">
        <h3 class="section-title">选项</h3>
        <van-cell-group inset>
          <van-cell title="生成 AI 药膳方案（Agent3）" center>
            <template #right-icon>
              <van-switch v-model="enableRecipe" size="20" active-color="#0d8050" />
            </template>
          </van-cell>
        </van-cell-group>
        <p class="muted">
          开启后会多调用一次大模型生成药膳，耗时更长；关闭时药膳页只给出基于推荐药材的代茶饮组合。
        </p>
      </div>

      <div class="actions">
        <van-button block type="primary" color="#0d8050" :disabled="!chief.trim()" @click="nextStep">
          下一步 · 填写问卷
        </van-button>
      </div>
    </div>

    <!-- 步骤 2：问卷（9 维度 × 3 题） -->
    <div v-else-if="step === 1" class="step">
      <div class="progress-tip">
        已答 <b>{{ answeredCount }}</b> / {{ totalQuestions }} 题
        <van-progress
          :percentage="Math.round((answeredCount / totalQuestions) * 100)"
          color="#0d8050"
          :show-pivot="false"
        />
      </div>

      <van-collapse v-model="activeDims" accordion>
        <van-collapse-item
          v-for="dim in dimensions"
          :key="dim.key"
          :name="dim.key"
          :title="dim.label"
          :value="`${dimAnswered(dim)}/3`"
        >
          <div v-for="q in dim.questions" :key="q.id" class="question">
            <p class="q-text">
              {{ q.text }}
              <van-tag v-if="q.core" type="primary" size="mini" color="#0d8050">核心</van-tag>
            </p>
            <div class="scale">
              <span
                v-for="(lab, n) in SCALE"
                :key="n"
                :class="{ on: localAnswers[q.id] === n }"
                @click="localAnswers[q.id] = n"
              >
                <i>{{ n }}</i>{{ lab }}
              </span>
            </div>
          </div>
        </van-collapse-item>
      </van-collapse>

      <div class="actions">
        <van-button block plain @click="step = 0">上一步</van-button>
        <van-button block type="primary" color="#0d8050" :loading="submitting" @click="submit">
          {{ answeredCount < totalQuestions ? `提交（已答 ${answeredCount} 题）` : '提交并开始分析' }}
        </van-button>
      </div>
    </div>

    <!-- 步骤 3：SSE 流式分析 / 追问 -->
    <div v-else class="step">
      <StreamChat
        :text="sseText"
        :nodes="sseNodes"
        :running="sseRunning"
        :questions="questions"
        :error-msg="blockMsg"
      />

      <div v-if="needAnswer" class="answer-box">
        <van-field
          v-model="followAnswer"
          type="textarea"
          rows="3"
          placeholder="回答上面的问题，帮助系统进一步明确你的体质…"
        />
        <van-button block type="primary" color="#0d8050" :loading="submitting" @click="submitAnswer">
          提交回答
        </van-button>
      </div>

      <div v-else-if="!sseRunning && !blockMsg" class="actions">
        <van-button block type="primary" color="#0d8050" @click="goResult">查看完整结果</van-button>
        <van-button block plain @click="restart">重新测试</van-button>
      </div>

      <div v-if="blockMsg" class="actions">
        <van-button block plain @click="restart">返回修改描述</van-button>
      </div>
    </div>

    <div class="disclaimer-bar">
      体质判定依据 GB/T 46939—2025 等级计分法，为确定性算法；结论不构成医疗诊断。
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showDialog, showToast } from 'vant'
import StreamChat from '@/components/StreamChat.vue'
import { useSSE } from '@/composables/useSSE'
import { BIZ_CODE, answerConsultation, getQuestionnaire } from '@/api'
import { useConsultStore } from '@/stores/consult'

const router = useRouter()
const consult = useConsultStore()

const GROUP_OPTIONS = ['孕妇', '哺乳期', '儿童', '老年人', '慢性病患者']
const SCALE = { 1: '没有', 2: '很少', 3: '有时', 4: '经常', 5: '总是' }

const step = ref(0)
const chief = ref(consult.chiefComplaint)
const groups = ref([])
const enableRecipe = ref(false)
const dimensions = ref([])
const totalQuestions = ref(27)
const activeDims = ref('')
const localAnswers = reactive({ ...consult.answers })
const submitting = ref(false)

const needAnswer = ref(false)
const followAnswer = ref('')
const currentId = ref('')
const blockMsg = ref('')
const questions = ref([])

const answeredCount = computed(() => Object.values(localAnswers).filter((v) => v >= 1).length)

/* ------------------------- SSE 流式（清单 5.6.3） ------------------------- */
const sse = useSSE('/api/v1/consultation/stream', {
  onEvent: (event, payload) => {
    if (event === 'meta') {
      llmSource.value = payload?.provider ? `${payload.provider}:${payload.model || ''}` : ''
    }
    if (event === 'question') {
      needAnswer.value = true
      questions.value.push(payload?.text || '')
    }
    if (event === 'done') {
      currentId.value = payload?.consultation_id || ''
      if (payload?.phase === 'follow_up') needAnswer.value = true
      if (payload?.phase === 'completed' && currentId.value) {
        // 流式播完直接进结果页
        setTimeout(() => router.replace(`/result/${currentId.value}`), 600)
      }
    }
    if (event === 'error') {
      blockMsg.value = payload?.message || '分析被中断'
      currentId.value = payload?.consultation_id || ''
      if (payload?.code === 'EMERGENCY_BLOCKED' || payload?.code === BIZ_CODE.EMERGENCY_BLOCKED) {
        showDialog({
          title: '请立即就医',
          message: payload.message,
          theme: 'round-button',
          confirmButtonText: '我知道了'
        })
      }
    }
  },
  // 6.2.4：超时 / 网络中断要给用户可见反馈，否则界面只会一直转圈
  onError: (e) => {
    blockMsg.value = e?.message || '网络连接异常，请稍后重试'
  }
})
const llmSource = ref('')
const sseText = computed(() => sse.text.value)
const sseNodes = computed(() => sse.nodes.value)
const sseRunning = computed(() => sse.running.value)

/* ------------------------------ 问卷加载 ------------------------------ */
onMounted(async () => {
  try {
    const d = await getQuestionnaire()
    dimensions.value = (d.dimensions || []).map((x) => ({
      key: x.dimension || x.name,
      label: x.label || x.name,
      questions: x.questions || []
    }))
    totalQuestions.value = d.total_questions || 27
    if (dimensions.value.length) activeDims.value = dimensions.value[0].key
  } catch {
    showToast('问卷加载失败')
  }
})

function toggleGroup(g) {
  const i = groups.value.indexOf(g)
  if (i >= 0) groups.value.splice(i, 1)
  else groups.value.push(g)
}

function dimAnswered(dim) {
  return (dim.questions || []).filter((q) => localAnswers[q.id] >= 1).length
}

function nextStep() {
  consult.setChief(chief.value)
  step.value = 1
}

function cleanAnswers() {
  const out = {}
  for (const [k, v] of Object.entries(localAnswers)) {
    if (v >= 1 && v <= 5) out[k] = v
  }
  return out
}

async function submit() {
  if (answeredCount.value === 0) {
    showToast('请至少回答一题')
    return
  }
  submitting.value = true
  step.value = 2
  blockMsg.value = ''
  needAnswer.value = false
  questions.value = []
  Object.entries(localAnswers).forEach(([k, v]) => consult.setAnswer(k, v))

  await sse.start({
    chief_complaint: chief.value,
    questionnaire: cleanAnswers(),
    special_groups: groups.value,
    enable_recipe: enableRecipe.value
  })
  submitting.value = false
}

async function submitAnswer() {
  if (!followAnswer.value.trim()) {
    showToast('请填写回答')
    return
  }
  submitting.value = true
  try {
    const res = await answerConsultation(currentId.value, { answer: followAnswer.value })
    consult.setResult(currentId.value, res)
    if (res.phase === 'completed') {
      router.replace(`/result/${currentId.value}`)
    } else {
      questions.value.push(...(res.follow_up_questions || []))
      followAnswer.value = ''
    }
  } catch (e) {
    showToast(e.message || '提交失败')
  } finally {
    submitting.value = false
  }
}

function goResult() {
  if (currentId.value) router.replace(`/result/${currentId.value}`)
}

function restart() {
  consult.clear()
  Object.keys(localAnswers).forEach((k) => delete localAnswers[k])
  sse.reset()
  step.value = 0
  blockMsg.value = ''
  needAnswer.value = false
  questions.value = []
}
</script>

<style scoped>
.step {
  padding-top: 0;
}
.progress-tip {
  padding: 12px 16px 4px;
  font-size: 12px;
  color: var(--c-text-sub);
}
.question {
  padding: 8px 0 12px;
  border-bottom: 1px dashed var(--c-border);
}
.question:last-child {
  border-bottom: none;
}
.q-text {
  margin: 0 0 8px;
  font-size: 13.5px;
  line-height: 1.6;
}
.scale {
  display: flex;
  gap: 4px;
}
.scale span {
  flex: 1;
  text-align: center;
  font-size: 11px;
  color: var(--c-text-sub);
  border: 1px solid var(--c-border);
  border-radius: 14px;
  padding: 3px 0;
}
.scale span i {
  display: block;
  font-style: normal;
  font-size: 10px;
  opacity: 0.6;
}
.scale span.on {
  background: var(--c-primary);
  border-color: var(--c-primary);
  color: #fff;
}
.scale span.on i {
  opacity: 0.85;
}
.actions {
  padding: 16px 16px 24px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.answer-box {
  padding: 10px 16px 24px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>
