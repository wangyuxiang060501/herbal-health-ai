<template>
  <div v-if="loading" class="loading-state">
    <van-loading size="22" vertical color="#0d8050">{{ text }}</van-loading>
  </div>
  <div v-else-if="error" class="loading-state">
    <van-empty :description="error" image="error">
      <van-button v-if="retryable" size="small" type="primary" color="#0d8050" @click="$emit('retry')">
        重试
      </van-button>
    </van-empty>
  </div>
  <div v-else-if="empty" class="loading-state">
    <van-empty :description="emptyText" />
  </div>
  <slot v-else />
</template>

<script setup>
defineProps({
  loading: Boolean,
  error: { type: String, default: '' },
  empty: Boolean,
  emptyText: { type: String, default: '暂无数据' },
  text: { type: String, default: '加载中…' },
  retryable: { type: Boolean, default: true }
})
defineEmits(['retry'])
</script>

<style scoped>
.loading-state {
  padding: 40px 0;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 160px;
}
</style>
