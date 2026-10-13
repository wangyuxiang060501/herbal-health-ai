<template>
  <div class="page">
    <van-nav-bar title="药材库" fixed placeholder />

    <div class="search-bar">
      <van-search
        v-model="keyword"
        placeholder="搜索药材，如 黄芪 / 附子"
        shape="round"
        background="#f5f7f5"
        @search="onSearch"
        @cancel="onReset"
        show-action
      >
        <template #action>
          <div @click="onSearch">搜索</div>
        </template>
      </van-search>
    </div>

    <div class="filters">
      <van-dropdown-menu active-color="#0d8050">
        <van-dropdown-item v-model="category" :options="categoryOptions" title="类别" />
        <van-dropdown-item v-model="meridian" :options="meridianOptions" title="归经" />
        <van-dropdown-item v-model="foodOnly" :options="foodOptions" title="范围" />
      </van-dropdown-menu>
    </div>

    <!-- 搜索模式：直接展示搜索结果 -->
    <div v-if="searchMode">
      <LoadingState :loading="loading" :error="error" :empty="!herbs.length" empty-text="没有找到相关药材" @retry="onSearch">
        <div class="list">
          <HerbCard v-for="h in herbs" :key="h.id" :herb="h" @click="goDetail" />
        </div>
      </LoadingState>
    </div>

    <!-- 列表模式：分页 + 下拉加载 -->
    <div v-else>
      <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
        <van-list
          v-model:loading="listLoading"
          :finished="finished"
          finished-text="没有更多了"
          :error="!!error"
          error-text="加载失败，点击重试"
          @load="onLoad"
        >
          <div class="list">
            <HerbCard v-for="h in herbs" :key="h.id" :herb="h" @click="goDetail" />
          </div>
        </van-list>
      </van-pull-refresh>
      <van-empty v-if="!herbs.length && !listLoading && finished" description="没有符合条件的药材" />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import HerbCard from '@/components/HerbCard.vue'
import LoadingState from '@/components/LoadingState.vue'
import { getCategories, getMeridians, listHerbs, searchHerbs } from '@/api'

const router = useRouter()

const keyword = ref('')
const herbs = ref([])
const loading = ref(false)
const listLoading = ref(false)
const refreshing = ref(false)
const finished = ref(false)
const error = ref('')
const page = ref(1)
const size = 20
const total = ref(0)
const searchMode = ref(false)

const category = ref('')
const meridian = ref('')
const foodOnly = ref('')
const categories = ref([])
const meridians = ref([])

const categoryOptions = computed(() => [
  { text: '全部类别', value: '' },
  ...categories.value.map((c) => ({ text: `${c.name}（${c.count}）`, value: c.name }))
])
// 归经字段是复合串（如"肺肝经"），前端按包含匹配
const meridianOptions = computed(() => [
  { text: '全部归经', value: '' },
  ...meridians.value.map((m) => ({
    text: `${m.meridian || m.name}（${m.count ?? ''}）`,
    value: m.meridian || m.name
  }))
])
const foodOptions = [
  { text: '全部', value: '' },
  { text: '仅药食同源', value: '1' },
  { text: '仅查询类', value: '0' }
]

onMounted(async () => {
  try {
    const [c, m] = await Promise.all([getCategories(), getMeridians()])
    categories.value = Array.isArray(c) ? c : []
    meridians.value = Array.isArray(m) ? m : []
  } catch {
    showToast('筛选选项加载失败')
  }
})

watch([category, meridian, foodOnly], () => {
  if (searchMode.value) return
  resetAndLoad()
})

async function onLoad() {
  if (searchMode.value) return
  error.value = ''
  try {
    const params = { page: page.value, size }
    if (category.value) params.category = category.value
    if (meridian.value) params.meridian = meridian.value
    if (foodOnly.value !== '') params.is_food_medicine = foodOnly.value === '1'
    const data = await listHerbs(params)
    total.value = data.total
    const items = data.items || []
    herbs.value.push(...items)
    finished.value = herbs.value.length >= data.total
    page.value += 1
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    listLoading.value = false
    refreshing.value = false
  }
}

async function onSearch() {
  const q = keyword.value.trim()
  if (!q) {
    onReset()
    return
  }
  searchMode.value = true
  loading.value = true
  error.value = ''
  try {
    herbs.value = await searchHerbs(q, 50)
  } catch (e) {
    // 404 = 业务"没找到"，不是错误
    if (e.code === 404) herbs.value = []
    else error.value = e.message || '搜索失败'
  } finally {
    loading.value = false
  }
}

function onReset() {
  searchMode.value = false
  keyword.value = ''
  resetAndLoad()
}

function resetAndLoad() {
  herbs.value = []
  page.value = 1
  finished.value = false
  listLoading.value = true
  onLoad()
}

function onRefresh() {
  resetAndLoad()
}

function goDetail(h) {
  router.push(`/herbs/${h.id}`)
}
</script>

<style scoped>
/* van-nav-bar 已用 placeholder 占位，这里无需再留顶部空间 */
.list {
  padding: 10px 12px 20px;
}
</style>
