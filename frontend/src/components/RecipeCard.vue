<template>
  <div ref="cardEl" class="recipe-card">
    <div class="rc-head">
      <span class="rc-badge">{{ constitution }}调理</span>
      <span class="rc-date">{{ dateText }}</span>
    </div>

    <h3 class="rc-title">{{ title }}</h3>

    <div class="rc-block">
      <b>配伍</b>
      <div class="rc-herbs">
        <span v-for="h in herbs" :key="h.name" class="rc-herb">
          {{ h.name }}<i>{{ h.dosage || '适量' }}</i>
        </span>
      </div>
    </div>

    <div v-if="recipe" class="rc-block">
      <b>做法</b>
      <p class="rc-text">{{ recipe }}</p>
    </div>
    <div v-else class="rc-block">
      <b>做法</b>
      <p class="rc-text">{{ defaultMethod }}</p>
    </div>

    <div v-if="cautions.length" class="rc-block">
      <b>禁忌</b>
      <p class="rc-text">{{ cautions.join('；') }}</p>
    </div>

    <div class="rc-foot">
      <span>药食同源 · 智慧康养</span>
      <span>本卡片仅为日常食疗方向参考，非医疗处方</span>
    </div>

    <div class="rc-actions">
      <van-button size="small" icon="photo-o" type="primary" color="#0d8050" @click="saveImage">
        保存为图片
      </van-button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { showLoadingToast, showToast } from 'vant'

const props = defineProps({
  constitution: { type: String, default: '平和' },
  herbs: { type: Array, default: () => [] },
  recipe: { type: String, default: '' },
  cautions: { type: Array, default: () => [] }
})

const cardEl = ref(null)

const title = computed(() => `${props.constitution}药膳建议`)
const dateText = computed(() => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
})
const defaultMethod = computed(() => {
  if (!props.herbs.length) return '暂无推荐药材。'
  const names = props.herbs.map((h) => h.name).join('、')
  return `取${names}，加水 500ml 浸泡 20 分钟后小火煎煮 15 分钟，取汁温服，每日 1 剂。`
})

async function saveImage() {
  if (!cardEl.value) return
  const toast = showLoadingToast({ message: '生成图片…', forbidClick: true, duration: 0 })
  try {
    // 动态引入，避免首屏打包体积
    const { default: html2canvas } = await import('html2canvas')
    const canvas = await html2canvas(cardEl.value, {
      backgroundColor: '#ffffff',
      scale: Math.min(window.devicePixelRatio || 1, 3),
      useCORS: true
    })
    const url = canvas.toDataURL('image/png')
    const a = document.createElement('a')
    a.href = url
    a.download = `${title.value}-${dateText.value}.png`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    showToast('已保存，可到相册/下载查看')
  } catch (e) {
    showToast('生成失败：' + (e.message || '未知错误'))
  } finally {
    toast.close()
  }
}
</script>

<style scoped>
.recipe-card {
  background: linear-gradient(180deg, #fbfdfc 0%, #ffffff 100%);
  border: 1px solid #d6ecdf;
  border-radius: 14px;
  padding: 14px;
}
.rc-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.rc-badge {
  background: var(--c-primary-light);
  color: var(--c-primary);
  font-size: 11px;
  border-radius: 10px;
  padding: 2px 8px;
}
.rc-date {
  font-size: 11px;
  color: var(--c-text-sub);
}
.rc-title {
  margin: 10px 0 12px;
  font-size: 18px;
  color: var(--c-text);
}
.rc-block {
  margin-bottom: 10px;
}
.rc-block b {
  display: block;
  font-size: 12px;
  color: var(--c-primary);
  margin-bottom: 4px;
}
.rc-herbs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.rc-herb {
  background: #f5f7f5;
  border-radius: 14px;
  padding: 3px 10px;
  font-size: 12.5px;
}
.rc-herb i {
  font-style: normal;
  color: var(--c-text-sub);
  font-size: 11px;
  margin-left: 4px;
}
.rc-text {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.8;
  color: #3f4752;
  white-space: pre-wrap;
}
.rc-foot {
  border-top: 1px dashed var(--c-border);
  padding-top: 8px;
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 10.5px;
  color: var(--c-text-sub);
}
.rc-actions {
  margin-top: 10px;
  text-align: right;
}
</style>
