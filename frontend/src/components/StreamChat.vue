<template>
  <div class="stream-chat">
    <!-- 节点进度：由后端 node 事件驱动，不是前端伪造的假进度 -->
    <div v-if="nodes.length" class="nodes">
      <div v-for="(n, i) in nodes" :key="i" class="node-line">
        <van-icon name="success" color="#0d8050" size="13" />
        <span class="node-label">{{ n.label || n.node }}</span>
        <span v-if="n.summary" class="node-sum">{{ formatSummary(n.summary) }}</span>
      </div>
    </div>

    <!-- 结论流式文本（打字机） -->
    <div v-if="text || running" class="bubble ai">
      <span class="txt">{{ text }}</span>
      <span v-if="running" class="caret" />
    </div>

    <!-- 追问气泡 -->
    <div v-for="(q, i) in questions" :key="'q' + i" class="bubble ai question">
      <van-icon name="question-o" size="14" />
      <span>{{ q }}</span>
    </div>

    <div v-if="errorMsg" class="bubble system">
      <van-icon name="warning-o" size="14" />
      <span>{{ errorMsg }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({
  text: { type: String, default: '' },
  nodes: { type: Array, default: () => [] },
  questions: { type: Array, default: () => [] },
  running: Boolean,
  errorMsg: { type: String, default: '' }
})

function formatSummary(s) {
  if (!s || typeof s !== 'object') return ''
  return Object.entries(s)
    .map(([k, v]) => `${k}=${v}`)
    .join(' · ')
}
</script>

<style scoped>
.stream-chat {
  padding: 10px 12px;
}
.nodes {
  background: #fff;
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 10px;
}
.node-line {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  padding: 3px 0;
  color: #3f4752;
}
.node-label {
  font-weight: 500;
}
.node-sum {
  color: var(--c-text-sub);
  font-size: 11px;
  margin-left: auto;
  max-width: 45%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bubble {
  background: #fff;
  border-radius: 12px;
  padding: 12px 14px;
  font-size: 13.5px;
  line-height: 1.8;
  color: #1f2329;
  margin-bottom: 8px;
  white-space: pre-wrap;
  word-break: break-word;
}
.bubble.ai {
  border-top-left-radius: 3px;
}
.bubble.question {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  background: #eef6f1;
  color: #0d5c39;
}
.bubble.system {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  background: #fff8e6;
  color: #8a5a00;
}
.caret {
  display: inline-block;
  width: 2px;
  height: 15px;
  background: var(--c-primary);
  vertical-align: text-bottom;
  margin-left: 2px;
  animation: blink 0.9s steps(1) infinite;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}
</style>
