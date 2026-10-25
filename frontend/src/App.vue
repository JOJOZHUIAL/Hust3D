<template>
  <div class="app-root">
    <router-view />
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { showNotify, showConfirmDialog } from 'vant'
import { useAuthStore } from './store/auth'
import { getUserInfo } from './api/user'
import { getNotificationUnread, getNotificationList } from './api/notification'
import { getLatestAppRelease } from './api/app'
import { setUnread, unreadCount } from './store/notification'
import { isNative, getServerBase, assetUrl } from './utils/server'

const auth = useAuthStore()
let timer = null
let lastCount = null // 首轮只校准，不弹横幅

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
  // 安卓返回键：有路由历史时回退，仅在首页/无历史时退出 App
  // （默认行为是历史栈一浅就整个退出，导致子页面按返回直接闪退）
  if (isNative()) {
    import('@capacitor/app').then(({ App: CapApp }) => {
      CapApp.addListener('backButton', ({ canGoBack }) => {
        if (canGoBack) window.history.back()
        else CapApp.exitApp()
      })
    }).catch(() => {})
  }
  // App 内申请系统通知权限（安卓 13+ 必须运行时申请，否则横幅/系统通知不显示）
  if (isNative()) {
    import('@capacitor/local-notifications').then(async ({ LocalNotifications }) => {
      const p = await LocalNotifications.checkPermissions()
      if (p.display !== 'granted') await LocalNotifications.requestPermissions()
    }).catch(() => {})
    // 检查 App 是否有新版本（管理员在后台上传 APK 后提示更新）
    checkAppUpdate()
  }
  pollUnread()
  // 全局轮询未读通知：横幅提醒 + 角标数字（页面隐藏时跳过）
  timer = setInterval(pollUnread, 8000)
})

onUnmounted(() => clearInterval(timer))

// 把后端返回的纯文本更新说明转义后换行，避免管理员填写的内容当成 HTML 执行
function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ))
}

// 检查 App 新版本：仅在 App（非浏览器）内有意义
async function checkAppUpdate() {
  if (!isNative() || !getServerBase()) return
  try {
    const latest = await getLatestAppRelease()
    if (!latest || !latest.version_code) return

    const { App: CapApp } = await import('@capacitor/app')
    const info = await CapApp.getInfo() // { version: 版本名, build: versionCode }
    const current = Number(info?.build || 0)
    if (Number(latest.version_code) <= current) return

    const noteHtml = escapeHtml(
      latest.note || '有新的版本可用，建议更新到最新版本。',
    ).replace(/\n/g, '<br>')
    const sizeHtml = latest.size_text
      ? `<br><br><span style="color:#969799;font-size:12px">安装包 ${latest.size_text}</span>`
      : ''

    try {
      await showConfirmDialog({
        title: `发现新版本 ${latest.version_name || latest.version_code}`,
        message: noteHtml + sizeHtml,
        allowHtml: true,
        confirmButtonText: '立即更新',
        cancelButtonText: '稍后',
      })
    } catch (e) {
      return // 选了「稍后」
    }

    // 交给系统浏览器下载 APK（Capacitor 对非同源地址会用系统打开）
    window.location.href = assetUrl(latest.file_url)
  } catch (e) {
    /* 检查更新失败不影响使用 */
  }
}

async function pollUnread() {
  if (!auth.isLogin || document.hidden) return
  try {
    const { count } = await getNotificationUnread(true)
    const prev = lastCount
    lastCount = count
    setUnread(count)

    // App 内有新增未读 → 系统横幅通知（App 切后台也能收到提醒）+ 页内横幅
    if (prev !== null && count > prev) {
      const list = await getNotificationList(true)
      const latest = list[0]
      if (latest) {
        showNotify({ type: 'primary', message: latest.title, duration: 3500 })
        if (isNative()) {
          // 动态引入，浏览器端不加载原生模块
          const { LocalNotifications } = await import('@capacitor/local-notifications')
          LocalNotifications.schedule({
            notifications: [{
              id: latest.id % 2147483647 || Date.now() % 2147483647,
              title: latest.title,
              body: latest.body || '',
            }],
          }).catch(() => {})
        }
      }
    }
  } catch (e) {
    /* 静默轮询失败忽略 */
  }
}

// 未读数清零时同步清理系统通知（供通知中心"全部已读"后调用）
window.__clearAppBadge = () => {
  setUnread(0)
  lastCount = 0
  if (isNative()) {
    import('@capacitor/local-notifications').then(({ LocalNotifications }) => {
      LocalNotifications.getDeliveredNotifications().then(({ notifications }) => {
        if (notifications.length) {
          LocalNotifications.removeDeliveredNotifications({ notifications: notifications.map((n) => n.id) })
        }
      }).catch(() => {})
    }).catch(() => {})
  }
}
</script>

<style scoped>
.app-root {
  min-height: 100vh;
}
</style>
