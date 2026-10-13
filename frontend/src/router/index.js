import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'home', component: () => import('@/views/HomeView.vue'), meta: { tab: true } },
  {
    path: '/herbs',
    name: 'herbs',
    component: () => import('@/views/HerbListView.vue'),
    meta: { tab: true }
  },
  {
    path: '/herbs/:id',
    name: 'herb-detail',
    component: () => import('@/views/HerbDetailView.vue')
  },
  {
    path: '/test',
    name: 'test',
    component: () => import('@/views/TestView.vue'),
    meta: { tab: true, requireDisclaimer: true }
  },
  {
    path: '/result/:id',
    name: 'result',
    component: () => import('@/views/ResultView.vue')
  },
  {
    path: '/recipe/:id',
    name: 'recipe',
    component: () => import('@/views/RecipeView.vue')
  },
  {
    path: '/history/:id',
    name: 'history-detail',
    component: () => import('@/views/HistoryDetailView.vue')
  },
  {
    path: '/mine',
    name: 'mine',
    component: () => import('@/views/MineView.vue'),
    meta: { tab: true }
  },
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue') },
  { path: '/about', name: 'about', component: () => import('@/views/AboutView.vue') },
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 })
})

/**
 * 路由守卫（清单 5.1.6）
 *
 * 后端尚未实现用户认证（user 模块只提供 history/trend），因此这里不做
 * 强制登录跳转，改为「免责声明未确认 → 先确认」这一条真实生效的守卫。
 * 等后端补上 /api/v1/auth 后，在此处追加 token 校验即可。
 */
router.beforeEach((to) => {
  if (to.meta.requireDisclaimer) {
    const accepted = localStorage.getItem('disclaimer_accepted')
    if (!accepted) {
      sessionStorage.setItem('pending_route', to.fullPath)
      return { name: 'about', query: { next: to.fullPath } }
    }
  }
  return true
})

export default router
