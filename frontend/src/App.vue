<template>
  <div class="app-root">
    <router-view v-slot="{ Component }">
      <transition name="fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>

    <TabBar v-if="showTab" />
    <DisclaimerModal v-model="showDisclaimer" @accept="onAccept" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import TabBar from '@/components/TabBar.vue'
import DisclaimerModal from '@/components/DisclaimerModal.vue'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const user = useUserStore()

const showTab = computed(() => !!route.meta.tab)
const showDisclaimer = ref(false)

// 首次进入应用强制确认免责声明（清单 5.6.2 流程起点）
onMounted(() => {
  if (!user.disclaimerAccepted) showDisclaimer.value = true
})

function onAccept() {
  user.acceptDisclaimer()
  showDisclaimer.value = false
  const next = sessionStorage.getItem('pending_route')
  if (next && route.fullPath !== next) {
    sessionStorage.removeItem('pending_route')
    router.replace(next)
  }
}

// 从 /about 页手动打开时用（点击"查看免责声明"）
watch(
  () => route.query.disclaimer,
  (v) => {
    if (v === '1') showDisclaimer.value = true
  },
  { immediate: true }
)
</script>

<style>
.app-root {
  min-height: 100vh;
  background: var(--c-bg);
}
</style>
