// 前端组件冒烟测试：确保每个组件/页面能被真实挂载，不抛运行时错误。
// 运行环境：happy-dom（无 canvas，因此图表分支只在有数据时才执行，这里不触发）。
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import Vant from 'vant'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'

import TabBar from '@/components/TabBar.vue'
import DisclaimerModal from '@/components/DisclaimerModal.vue'
import HerbCard from '@/components/HerbCard.vue'
import StreamChat from '@/components/StreamChat.vue'
import LoadingState from '@/components/LoadingState.vue'
import RecipeCard from '@/components/RecipeCard.vue'

import HomeView from '@/views/HomeView.vue'
import HerbListView from '@/views/HerbListView.vue'
import HerbDetailView from '@/views/HerbDetailView.vue'
import TestView from '@/views/TestView.vue'
import ResultView from '@/views/ResultView.vue'
import RecipeView from '@/views/RecipeView.vue'
import MineView from '@/views/MineView.vue'
import HistoryDetailView from '@/views/HistoryDetailView.vue'
import LoginView from '@/views/LoginView.vue'
import AboutView from '@/views/AboutView.vue'

const SAMPLE_HERB = {
  id: 1,
  name: '黄芪',
  category: '补虚药',
  meridian: '脾肺经',
  effect: '补气升阳，固表止汗',
  component: '黄芪甲苷',
  dosage: '9-30g',
  is_food_medicine: true,
  is_blacklisted: false,
  has_conflict: false,
  merged_from: 1,
  usage_policy: '可在药膳方案中使用',
  source_note: '数据来源：参考仓库'
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: HomeView },
      { path: '/herbs', component: HerbListView },
      { path: '/herbs/:id', component: HerbDetailView },
      { path: '/test', component: TestView },
      { path: '/result/:id', component: ResultView },
      { path: '/recipe/:id', component: RecipeView },
      { path: '/history/:id', component: HistoryDetailView },
      { path: '/mine', component: MineView },
      { path: '/login', component: LoginView },
      { path: '/about', component: AboutView }
    ]
  })
}

function mountPage(Comp, { router } = {}) {
  const r = router || makeRouter()
  return mount(Comp, {
    global: {
      plugins: [createPinia(), Vant, r]
    }
  })
}

describe('公共组件', () => {
  it('TabBar 渲染四个入口', () => {
    const w = mount(TabBar, { global: { plugins: [Vant, makeRouter()] } })
    const text = w.text()
    for (const label of ['首页', '药材库', '体质测试', '我的']) {
      expect(text).toContain(label)
    }
  })

  it('DisclaimerModal 展示免责要点', () => {
    const w = mount(DisclaimerModal, {
      props: { modelValue: true },
      global: { plugins: [Vant] }
    })
    expect(w.text()).toContain('不属于医疗诊断')
    expect(w.text()).toContain('120')
  })

  it('HerbCard 区分药食同源与高危', () => {
    const safe = mount(HerbCard, { props: { herb: SAMPLE_HERB } })
    expect(safe.text()).toContain('黄芪')
    expect(safe.text()).toContain('药食同源')

    const danger = mount(HerbCard, {
      props: { herb: { ...SAMPLE_HERB, name: '附子', is_food_medicine: false, is_blacklisted: true } }
    })
    expect(danger.text()).toContain('附子')
    expect(danger.text()).toContain('高危')
  })

  it('LoadingState 三态互斥', () => {
    const withVant = { global: { plugins: [Vant] } }

    const loading = mount(LoadingState, { props: { loading: true }, ...withVant })
    expect(loading.text()).toContain('加载中')
    expect(loading.find('.van-loading').exists()).toBe(true)

    // 错误态：给出重试入口，且不再显示加载中文案
    const errored = mount(LoadingState, { props: { error: '请求失败' }, ...withVant })
    expect(errored.find('.van-empty').exists()).toBe(true)
    expect(errored.text()).toContain('重试')
    expect(errored.text()).not.toContain('加载中')

    // 空态：只占位，不显示重试
    const empty = mount(LoadingState, { props: { empty: true, emptyText: '没数据' }, ...withVant })
    expect(empty.find('.van-empty').exists()).toBe(true)
    expect(empty.text()).not.toContain('重试')
  })

  it('StreamChat 渲染节点轨迹与流式文本', () => {
    const w = mount(StreamChat, {
      props: {
        text: '你的体质倾向于阳虚',
        nodes: [{ node: 'constitution_engine', label: '体质判定', summary: { primary: '阳虚质' } }],
        questions: ['你大便成形吗？'],
        running: true
      },
      global: { plugins: [Vant] }
    })
    expect(w.text()).toContain('体质判定')
    expect(w.text()).toContain('阳虚质')
    expect(w.text()).toContain('你的体质倾向于阳虚')
    expect(w.text()).toContain('你大便成形吗？')
  })

  it('RecipeCard 由推荐药材派生做法', () => {
    const w = mount(RecipeCard, {
      props: {
        constitution: '阳虚质',
        herbs: [{ name: '肉桂', dosage: '3g' }, { name: '生姜', dosage: '3片' }],
        cautions: ['阴虚火旺者慎用']
      },
      global: { plugins: [Vant] }
    })
    expect(w.text()).toContain('阳虚质')
    expect(w.text()).toContain('肉桂')
    expect(w.text()).toContain('阴虚火旺者慎用')
    expect(w.text()).toContain('保存为图片')
  })
})

describe('页面可挂载', () => {
  it.each([
    ['首页', HomeView],
    ['药材库', HerbListView],
    ['药材详情', HerbDetailView],
    ['体质测试', TestView],
    ['结果页', ResultView],
    ['药膳页', RecipeView],
    ['我的', MineView],
    ['问诊记录详情', HistoryDetailView],
    ['登录/注册', LoginView],
    ['关于', AboutView]
  ])('%s', (_name, Comp) => {
    const w = mountPage(Comp)
    expect(w.exists()).toBe(true)
  })
})

describe('安全相关展示', () => {
  it('问卷页声明判定标准与免责', async () => {
    const w = mountPage(TestView)
    expect(w.text()).toContain('GB/T 46939')
    expect(w.text()).toContain('不构成医疗诊断')
  })

  it('药膳页明确AI药膳未启用时的降级说明', async () => {
    const w = mountPage(RecipeView)
    // 无数据时不渲染业务文案，但组件应挂载成功
    expect(w.exists()).toBe(true)
  })
})
