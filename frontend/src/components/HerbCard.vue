<template>
  <div class="herb-card" @click="$emit('click', herb)">
    <div class="head">
      <span class="name">{{ herb.name }}</span>
      <span class="tags">
        <van-tag v-if="herb.is_blacklisted" type="danger">高危</van-tag>
        <van-tag v-else-if="herb.is_food_medicine" type="success" color="#0d8050">药食同源</van-tag>
        <van-tag v-else plain type="default">仅查询</van-tag>
        <van-tag v-if="herb.has_conflict" type="warning">数据有冲突</van-tag>
      </span>
    </div>

    <div class="meta">
      <span v-if="herb.category">{{ herb.category }}</span>
      <span v-if="herb.meridian">归 {{ herb.meridian }}</span>
      <span v-if="herb.dosage">{{ herb.dosage }}</span>
    </div>

    <p class="effect">{{ herb.effect || '暂无功效描述' }}</p>

    <div v-if="showPolicy" class="policy" :class="{ danger: herb.is_blacklisted }">
      {{ herb.usage_policy }}
    </div>
  </div>
</template>

<script setup>
defineProps({
  herb: { type: Object, required: true },
  showPolicy: { type: Boolean, default: true }
})
defineEmits(['click'])
</script>

<style scoped>
.herb-card {
  background: #fff;
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.name {
  font-size: 16px;
  font-weight: 600;
  color: var(--c-text);
}
.tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.meta {
  margin: 6px 0;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 11.5px;
  color: var(--c-text-sub);
}
.effect {
  margin: 0;
  font-size: 13px;
  color: #3f4752;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.policy {
  margin-top: 8px;
  font-size: 11px;
  color: #6b7280;
  background: #f5f7f5;
  border-radius: 6px;
  padding: 4px 8px;
}
.policy.danger {
  color: #c0392b;
  background: #fdecea;
}
</style>
