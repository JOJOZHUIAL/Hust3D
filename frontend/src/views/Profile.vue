<template>
  <div class="page profile">
    <div class="profile-header">
      <div class="avatar">{{ avatarText }}</div>
      <div class="p-name">{{ user?.name || '未绑定' }}</div>
      <div class="p-sub">{{ user ? `${user.student_id || ''} · ${user.college || ''}` : '' }}</div>
    </div>

    <div class="quota-box">
      <div class="q-label">本学期剩余打印次数</div>
      <div class="q-num">{{ remaining }}<span class="unit"> 次</span></div>
    </div>

    <van-cell-group inset>
      <van-cell v-if="isNative" title="服务器地址" :value="serverShort" icon="desktop-o" is-link @click="editServer" />
      <van-cell title="我的申请" icon="orders-o" is-link to="/applications" />
      <van-cell title="使用指南" icon="question-o" is-link to="/guide" />
      <van-cell
        v-if="isNative"
        title="检测更新"
        icon="replay"
        :value="appVersion ? `v${appVersion}` : ''"
        is-link
        @click="onCheckUpdate"
      />
      <van-cell
        title="联系工作室"
        icon="chat-o"
        is-link
        to="/chat"
      />
      <van-cell v-if="isAdmin" title="管理后台" icon="setting-o" is-link to="/admin" />
    </van-cell-group>

    <div class="logout-btn">
      <van-button round block plain type="danger" @click="onLogout">退出登录</van-button>
    </div>

    <!-- 发现新版本 -->
    <van-dialog
      v-model:show="updateShow"
      title="发现新版本"
      show-cancel-button
      confirm-button-text="立即更新"
      cancel-button-text="稍后再说"
      @confirm="doUpdate"
    >
      <div class="upd-box">
        <div class="upd-ver">v{{ updateInfo?.version_name || '' }}（{{ updateInfo?.version_code }}）</div>
        <div v-if="updateInfo?.note" class="upd-note">{{ updateInfo.note }}</div>
        <div class="upd-size" v-if="updateInfo?.file_size">
          大小 {{ (updateInfo.file_size / 1024 / 1024).toFixed(1) }} MB
        </div>
      </div>
    </van-dialog>

    <TabBar />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { showToast, showFailToast, showConfirmDialog } from 'vant'
import { getUserInfo, getQuota } from '../api/user'
import { logout } from '../api/auth'
import { useAuthStore } from '../store/auth'
import { isNative as isNativePlatform, getServerBase, setServerBase, assetUrl } from '../utils/server'
import { getLatestAppRelease } from '../api/app'
import TabBar from '../components/TabBar.vue'

const router = useRouter()
const auth = useAuthStore()
const user = computed(() => auth.user)
const isAdmin = computed(() => auth.isAdmin)
const remaining = ref(0)

// App 模式：查看/修改后端服务器地址
const isNative = isNativePlatform()
const serverShort = computed(() => getServerBase() || '未设置')

// —— 检测更新：对比 App 已装 versionCode 与服务器最新版本 ——
const appVersion = ref('')
const updateShow = ref(false)
const updateInfo = ref(null)

async function onCheckUpdate() {
  if (!isNativePlatform()) {
    showToast('网页版无需更新')
    return
  }
  try {
    const { App } = await import('@capacitor/app')
    const info = await App.getInfo()
    appVersion.value = info.version
    const latest = await getLatestAppRelease()
    if (latest && Number(latest.version_code) > Number(info.build)) {
      updateInfo.value = latest
      updateShow.value = true
    } else {
      showToast('已是最新版本')
    }
  } catch (e) {
    showToast('检查更新失败，请稍后重试')
  }
}

function doUpdate() {
  if (!updateInfo.value) return
  // WebView 里用 blob 下载触发安装（window.open 对 apk 无效）
  fetch(assetUrl(updateInfo.value.file_url))
    .then((r) => r.blob())
    .then((blob) => {
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = 'hust3d.apk'
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(a.href)
    })
    .catch(() => showFailToast('下载失败，请稍后重试'))
}

function editServer() {
  showConfirmDialog({
    title: '服务器地址',
    message: getServerBase() || '尚未设置',
    showCancelButton: true,
    confirmButtonText: '清除重设',
  })
    .then(() => {
      setServerBase('')
      showSuccessToast('已清除，请重新登录并填写服务器地址')
      setTimeout(() => location.reload(), 800)
    })
    .catch(() => {})
}

const avatarText = computed(() => (user.value?.name ? user.value.name[0] : '3D'))

onMounted(async () => {
  try {
    const info = await getUserInfo()
    auth.setUser(info)
    remaining.value = info.remaining_quota
  } catch (e) {
    /* 拦截器已处理 */
  }
  try {
    const q = await getQuota()
    remaining.value = q.remaining
  } catch (e) {
    /* 忽略 */
  }
})


async function onLogout() {
  try {
    await showConfirmDialog({ title: '退出登录', message: '确定退出当前账号吗？' })
  } catch (e) {
    return // 取消
  }
  try {
    await logout()
  } catch (e) {
    /* 忽略退出接口异常 */
  }
  auth.logout()
  // 回登录页
  router.replace({ name: 'login' })
}
</script>

<style scoped>
.upd-box {
  padding: 14px 16px 6px;
  text-align: center;
}
.upd-ver {
  font-size: 15px;
  font-weight: 600;
  color: #2f6bff;
}
.upd-note {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.7;
  color: #323233;
  white-space: pre-wrap;
  text-align: left;
}
.upd-size {
  margin-top: 6px;
  font-size: 12px;
  color: #969799;
}
.profile-header {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 32px 16px;
  background: linear-gradient(180deg, #2f6bff, #6f9bff);
}
.avatar {
  width: 64px;
  height: 64px;
  line-height: 64px;
  text-align: center;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.25);
  color: #fff;
  font-size: 26px;
  font-weight: 700;
}
.p-name {
  color: #fff;
  font-size: 18px;
  font-weight: 600;
}
.p-sub {
  color: rgba(255, 255, 255, 0.85);
  font-size: 13px;
}
.quota-box {
  margin: -16px 16px 16px;
  padding: 16px 20px;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.q-label {
  font-size: 14px;
  color: #646566;
}
.q-num {
  font-size: 28px;
  font-weight: 700;
  color: #2f6bff;
}
.q-num .unit {
  font-size: 13px;
  font-weight: 400;
  color: #969799;
}
.logout-btn {
  margin: 24px 16px 0;
}
</style>
