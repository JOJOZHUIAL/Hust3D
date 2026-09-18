<template>
  <div class="app-root">
    <router-view />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useAuthStore } from './store/auth'
import { getUserInfo } from './api/user'

const auth = useAuthStore()

// 启动时若有登录态，拉取一次最新用户信息，同步后端可能已更新的学院/角色等。
// 这样管理员配置、学院信息等后端数据变更后，用户刷新页面即可生效，无需退出重登。
onMounted(async () => {
  if (!auth.isLogin) return
  try {
    const info = await getUserInfo()
    auth.setUser(info)
  } catch (e) {
    /* 401 由拦截器统一处理并跳登录页，其余错误忽略 */
  }
})
</script>

<style scoped>
.app-root {
  min-height: 100vh;
}
</style>
