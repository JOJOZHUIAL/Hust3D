import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../store/auth'

// 采用 hash 路由，部署到 Nginx 静态目录无需额外回退配置。
const routes = [
  { path: '/', name: 'home', component: () => import('../views/Home.vue') },
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/Login.vue'),
    meta: { requiresAuth: false },
  },
  { path: '/apply', name: 'apply', component: () => import('../views/Apply.vue') },
  { path: '/applications', name: 'my-applications', component: () => import('../views/MyApplications.vue') },
  { path: '/application/:id', name: 'application-detail', component: () => import('../views/ApplicationDetail.vue') },
  { path: '/profile', name: 'profile', component: () => import('../views/Profile.vue') },
  { path: '/chat', name: 'chat', component: () => import('../views/Chat.vue') },
  { path: '/guide', name: 'guide', component: () => import('../views/Guide.vue') },
  { path: '/notices', name: 'notice-list', component: () => import('../views/NoticeList.vue') },
  { path: '/notifications', name: 'notifications', component: () => import('../views/Notifications.vue') },
  {
    path: '/notice/:id',
    name: 'notice-detail',
    component: () => import('../views/NoticeDetail.vue'),
  },
  { path: '/admin', name: 'admin-home', component: () => import('../views/admin/AdminHome.vue') },
  { path: '/admin/pending', name: 'admin-pending', component: () => import('../views/admin/AdminPending.vue') },
  { path: '/admin/chat', name: 'admin-chat', component: () => import('../views/admin/AdminChat.vue') },
  {
    path: '/admin/chat/:userId',
    name: 'admin-chat-room',
    component: () => import('../views/Chat.vue'),
  },
  {
    path: '/admin/notices',
    name: 'admin-notices',
    component: () => import('../views/admin/AdminNotices.vue'),
  },
  {
    path: '/admin/consumables',
    name: 'admin-consumables',
    component: () => import('../views/admin/Consumables.vue'),
  },
  {
    path: '/admin/admins',
    name: 'admin-admins',
    component: () => import('../views/admin/AdminAdmins.vue'),
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  const requiresAuth = to.meta.requiresAuth !== false

  // 登录页：已登录则直接进首页
  if (!requiresAuth) {
    if (to.name === 'login' && auth.isLogin) return { name: 'home' }
    return true
  }

  // 需要登录但未登录 → 去登录页
  if (!auth.isLogin) return { name: 'login' }

  return true
})

export default router
