import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
    { path: '/', redirect: '/qa' },
    { path: '/qa', name: 'qa', component: () => import('@/views/QAView.vue') },
    { path: '/kb', name: 'kb', component: () => import('@/views/KBListView.vue') },
    { path: '/kb/:id', name: 'kb-detail', component: () => import('@/views/KBDetailView.vue') },
    { path: '/eval', name: 'eval', component: () => import('@/views/EvalView.vue') },
    { path: '/monitor', name: 'monitor', component: () => import('@/views/MonitorView.vue') },
  ],
})

// 路由守卫：未登录跳转到 /login
router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  if (!to.meta.public && !token) {
    return { name: 'login' }
  }
})

export default router
