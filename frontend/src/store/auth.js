import { defineStore } from 'pinia'

// 登录态相关状态，持久化到 localStorage。
// - token：登录后由后端签发，随请求放在 Authorization 头
// - user：当前用户信息（含剩余配额）
export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem('hust3d_token') || '',
    user: JSON.parse(localStorage.getItem('hust3d_user') || 'null'),
  }),

  getters: {
    isLogin: (s) => !!s.token,
    isAdmin: (s) => !!s.user && ['admin', 'superadmin'].includes(s.user.role),
  },

  actions: {
    setToken(t) {
      this.token = t
      localStorage.setItem('hust3d_token', t)
    },
    setUser(u) {
      this.user = u
      localStorage.setItem('hust3d_user', JSON.stringify(u))
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('hust3d_token')
      localStorage.removeItem('hust3d_user')
    },
  },
})
