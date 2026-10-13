<template>
  <van-dialog
    v-model:show="inner"
    title="重要声明"
    :show-confirm-button="false"
    :close-on-click-overlay="false"
    theme="round-button"
  >
    <div class="dlg">
      <p class="warn">本系统提供的是<strong>中医体质倾向参考与日常食疗方向建议</strong>，不属于医疗诊断。</p>

      <ol>
        <li>本系统不提供疾病诊断、治疗方案、处方与用药指导，不能替代执业医师诊疗。</li>
        <li>若出现胸痛、呼吸困难、持续高热、意识障碍、大出血等急症表现，<strong>请立即就医或拨打 120</strong>，不要依赖本系统。</li>
        <li>推荐药材<strong>仅限国家药食同源目录内品种</strong>，附子、乌头等高危药材不会进入任何推荐方案。</li>
        <li>孕妇、哺乳期女性、儿童、慢性病患者及正在服药者，请先咨询医师或药师。</li>
        <li>个体体质存在差异，食用后如有不适请立即停止并就医。</li>
      </ol>

      <p class="muted">
        体质判定依据 GB/T 46939—2025 等级计分法（确定性算法，非大模型生成）。
      </p>

      <div class="btns">
        <van-button block plain @click="onReject">不同意并退出</van-button>
        <van-button block type="primary" color="#0d8050" @click="onAccept">
          我已阅读并同意
        </van-button>
      </div>
    </div>
  </van-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { showToast } from 'vant'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'accept', 'reject'])

const inner = ref(props.modelValue)
watch(
  () => props.modelValue,
  (v) => (inner.value = v)
)
watch(inner, (v) => emit('update:modelValue', v))

function onAccept() {
  emit('accept')
  inner.value = false
}

function onReject() {
  showToast('需同意声明后继续使用')
  emit('reject')
}
</script>

<style scoped>
.dlg {
  padding: 4px 8px 12px;
  max-height: 62vh;
  overflow-y: auto;
}
.warn {
  color: #c8553d;
  font-size: 13px;
  margin: 4px 0 10px;
}
ol {
  padding-left: 18px;
  margin: 0 0 10px;
  font-size: 12.5px;
  line-height: 1.75;
  color: #3f4752;
}
ol li {
  margin-bottom: 4px;
}
.muted {
  color: var(--c-text-sub);
  font-size: 11px;
}
.btns {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}
</style>
