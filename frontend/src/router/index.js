import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import LoginView from '../views/LoginView.vue'
import HomeView from '../views/HomeView.vue'
import RollsView from '../views/RollsView.vue'
import DipsView from '../views/DipsView.vue'
import LoftsView from '../views/LoftsView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
    { path: '/', name: 'rack', component: HomeView },
    { path: '/lofts', name: 'lofts', component: LoftsView, meta: { adminOnly: true } },
    { path: '/rolls', name: 'rolls', component: RollsView, meta: { secondary: true } },
    { path: '/dips', name: 'dips', component: DipsView, meta: { secondary: true } },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && auth.isAuthenticated) {
    return { name: 'rack' }
  }
  if (auth.isAuthenticated && !auth.user) {
    try {
      await auth.fetchMe()
    } catch {
      auth.logout()
      return { name: 'login' }
    }
  }
  // 改名台仅管理员可进；操作工手输网址也挡回晾晒架
  if (to.meta.adminOnly && auth.user?.role !== 'admin') {
    return { name: 'rack' }
  }
})

export default router
