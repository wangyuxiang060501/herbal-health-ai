<template>
  <van-tabbar v-model="active" route active-color="#0d8050" inactive-color="#6b7280" fixed>
    <van-tabbar-item replace to="/" icon="home-o">首页</van-tabbar-item>
    <van-tabbar-item replace to="/herbs" icon="flower-o">药材库</van-tabbar-item>
    <van-tabbar-item replace to="/test" icon="records">体质测试</van-tabbar-item>
    <van-tabbar-item replace to="/mine" icon="user-o">我的</van-tabbar-item>
  </van-tabbar>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const active = ref(0)
const order = ['/', '/herbs', '/test', '/mine']

watch(
  () => route.path,
  (p) => {
    const i = order.findIndex((x) => p === x || p.startsWith(x + '/'))
    if (i >= 0) active.value = i
  },
  { immediate: true }
)
</script>
