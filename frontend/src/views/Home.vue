<template>
  <div class="page home">
    <!-- 顶部主视觉：校园航拍 + 问候 -->
    <div class="hero">
      <div class="hero-inner">
        <div class="avatar">{{ avatarText }}</div>
        <div class="hello">
          <div class="greet">{{ greeting }}，{{ user?.name || user?.student_id || '同学' }}</div>
          <div class="sub">{{ user?.college || '欢迎使用 3D 打印服务' }}</div>
        </div>
        <img :src="hustRound" class="hero-badge" alt="哈尔滨理工大学" />
      </div>
    </div>

    <!-- 配额卡片 -->
    <div class="quota-card">
      <div class="quota-left">
        <div class="quota-label">本学期剩余打印次数</div>
        <div class="quota-num">{{ remaining }}<span class="unit"> 次</span></div>
      </div>
      <van-button
        v-if="remaining > 0"
        type="primary"
        round
        class="quota-btn"
        @click="$router.push('/apply')"
      >
        立即申请打印
      </van-button>
      <van-button v-else type="default" round class="quota-btn" disabled>
        次数已用完
      </van-button>
    </div>

    <!-- 快捷入口 -->
    <van-grid :column-num="4" :border="false" class="quick-grid">
      <van-grid-item to="/applications">
        <div class="q-icon" style="--c: #2f6bff"><van-icon name="records" /></div>
        <span class="q-text">我的申请</span>
      </van-grid-item>
      <van-grid-item to="/guide">
        <div class="q-icon" style="--c: #ff976a"><van-icon name="question-o" /></div>
        <span class="q-text">使用指南</span>
      </van-grid-item>
      <van-grid-item to="/chat">
        <div class="q-icon" style="--c: #07c160">
          <van-badge :content="unread > 0 ? String(unread) : undefined" max="99">
            <van-icon name="chat-o" />
          </van-badge>
        </div>
        <span class="q-text">联系工作室</span>
      </van-grid-item>
      <van-grid-item v-if="isAdmin" to="/admin">
        <van-badge :content="todoBadge > 0 ? String(todoBadge) : undefined" max="99">
          <div class="q-icon" style="--c: #7232dd"><van-icon name="setting-o" /></div>
        </van-badge>
        <span class="q-text">管理后台</span>
      </van-grid-item>
      <van-grid-item v-else @click="openFeedback">
        <van-badge :content="feedbackCount > 0 ? String(feedbackCount) : undefined" max="99">
          <div class="q-icon" style="--c: #7232dd"><van-icon name="photo-o" /></div>
        </van-badge>
        <span class="q-text">提交反馈</span>
      </van-grid-item>
    </van-grid>

    <!-- 待办任务：管理员看汇总（点击进入对应管理页），学生看逐条待办（带操作） -->
    <div v-if="todoItems.length" class="todo-card">
      <div class="todo-title">待办任务</div>

      <!-- 管理员：汇总行 -->
      <template v-if="isAdmin">
        <div v-for="t in todoItems" :key="t.kind" class="todo-row"
             @click="$router.push(t.cat ? `${t.link}?cat=${t.cat}` : t.link)">
          <div class="todo-icon" :style="{ '--c': t.color }"><van-icon :name="t.icon" /></div>
          <span class="todo-label">{{ t.label }}</span>
          <span class="todo-count" :class="{ zero: !t.count }">{{ t.count }}</span>
          <van-icon name="arrow" color="#c8c9cc" />
        </div>
      </template>

      <!-- 学生：逐条待办（待取件 / 待反馈） -->
      <template v-else>
        <div v-for="t in todoItems" :key="`${t.kind}-${t.id}`" class="todo-row" @click="$router.push(`/application/${t.id}`)">
          <div class="todo-icon" :style="{ '--c': t.kind === 'pickup' ? '#ff976a' : '#2f6bff' }">
            <van-icon :name="t.kind === 'pickup' ? 'gift-o' : 'photograph'" />
          </div>
          <div class="todo-main">
            <div class="todo-label">
              <van-tag :color="t.kind === 'pickup' ? '#ff976a' : '#2f6bff'" style="margin-right: 6px">
                {{ t.kind === 'pickup' ? '待取件' : '待反馈' }}
              </van-tag>
              <span class="todo-no">{{ t.apply_no }}</span>
            </div>
            <div class="todo-sub">{{ todoLabel(t) }}</div>
          </div>
          <van-button
            v-if="t.kind === 'pickup'"
            size="mini"
            type="primary"
            round
            :loading="picking"
            @click.stop="onPickupDone(t)"
          >
            已领取
          </van-button>
          <van-button
            v-else
            size="mini"
            type="success"
            round
            :loading="uploadingId === t.id"
            @click.stop="triggerUpload(t)"
          >
            上传反馈图
          </van-button>
        </div>
      </template>
    </div>

    <!-- 隐藏的文件选择器：上传反馈图（相册）/ 拍照 -->
    <input
      ref="fileInput"
      type="file"
      accept="image/*"
      class="hidden-file"
      @change="onFilePicked"
    />
    <input
      ref="cameraInput"
      type="file"
      accept="image/*"
      capture="environment"
      class="hidden-file"
      @change="onFilePicked"
    />

    <!-- 最新通知（默认折叠展示几条，点右侧箭头展开/收起） -->
    <div class="notify-title">
      最新通知
      <span
        v-if="canExpandNotices"
        class="notify-toggle"
        :class="{ open: noticesExpanded }"
        @click="toggleNotices"
      >
        <van-icon name="arrow" />
      </span>
    </div>
    <van-cell-group v-if="!notices.length" inset>
      <van-cell :title="noticesLoading ? '加载中…' : '暂无通知'" />
    </van-cell-group>
    <!-- 公告折叠展开：点条目在首页直接展开正文 -->
    <div v-else class="notice-box">
      <van-collapse v-model="activeNotice" accordion :border="false">
        <van-collapse-item
          v-for="n in shownNotices"
          :key="n.id"
          :name="n.id"
          :title="n.title"
          :label="`${n.publisher} · ${(n.created_at || '').slice(0, 10)}`"
        >
          <div class="notice-text">{{ noticeContents[n.id] ?? '加载中…' }}</div>
          <div
            class="notice-detail-link"
            @click.stop="$router.push({ name: 'notice-detail', params: { id: n.id } })"
          >
            查看详情 ›
          </div>
        </van-collapse-item>
      </van-collapse>
    </div>
    <div v-if="notices.length" class="notify-footer" @click="$router.push('/notices')">
      查看全部公告 ›
    </div>

    <!-- 取件提醒弹窗：打印件完成时在首页弹出 -->
    <van-popup
      v-model:show="pickupShow"
      round
      :close-on-click-overlay="false"
      :style="{ width: '86%', maxWidth: '420px' }"
    >
      <div class="pickup-box">
        <div class="pickup-icon"><van-icon name="gift-o" size="34" /></div>
        <div class="pickup-title">打印完成，请取件</div>
        <div class="pickup-sub">你的打印件已打印完成，请携带校园卡到工作室领取</div>

        <div class="pickup-list">
          <div v-for="it in pickupItems" :key="it.id" class="pickup-item">
            <div class="pi-head">
              <span class="pi-no">{{ it.application?.apply_no || it.title }}</span>
              <van-tag v-if="it.application?.picked_up" type="success">已领取</van-tag>
              <van-tag v-else type="warning">待取件</van-tag>
            </div>
            <div class="pi-file">{{ it.application?.file_name || '—' }}</div>
            <div class="pi-time">完成时间：{{ it.application?.completed_at || '—' }}</div>
          </div>
        </div>

        <p class="pickup-tip">
          取件后可上传实物图 / 现场照片反馈，成功奖励 1 次打印机会。
        </p>

        <div class="pickup-btns">
          <van-button round plain block @click="snoozePickup">稍后提醒</van-button>
          <van-button round type="primary" block @click="onPickupView">去查看</van-button>
        </div>
        <div class="pickup-ack" @click="onPickupAck">我知道了，不再提醒</div>
      </div>
    </van-popup>

    <!-- 待提交反馈：点首页「提交反馈」图标弹出，可直接选图/拍照上传 -->
    <van-popup v-model:show="feedbackShow" position="bottom" round :style="{ maxHeight: '80%' }">
      <div class="fb">
        <div class="fb-title">待提交反馈</div>
        <div class="fb-sub">上传实物图 / 现场照片即可，审核通过奖励打印次数</div>

        <van-empty v-if="!feedbackList.length" image-size="60" description="暂无待反馈的申请" />

        <div v-else class="fb-list">
          <div v-for="it in feedbackList" :key="it.id" class="fb-item">
            <div class="fb-info">
              <div class="fb-head">
                <span class="fb-no">{{ it.apply_no }}</span>
                <van-tag color="#ff976a" round>未反馈</van-tag>
              </div>
              <div class="fb-file">{{ it.file_name || '—' }}</div>
              <div class="fb-time">完成时间：{{ it.completed_at || '—' }}</div>
              <div v-if="it.feedback_deadline" class="fb-deadline">
                请在 {{ it.feedback_deadline }} 前反馈，逾期不再发放奖励
              </div>
            </div>
            <van-button
              size="small"
              type="success"
              round
              :loading="uploadingId === it.id"
              @click="triggerUpload(it)"
            >
              上传反馈图
            </van-button>
          </div>
        </div>

        <div class="fb-btns">
          <van-button round plain block @click="feedbackShow = false">关闭</van-button>
        </div>
      </div>
    </van-popup>

    <!-- App 内选图方式：拍照 / 相册 -->
    <van-action-sheet
      v-model:show="uploadSheetShow"
      :actions="uploadActions"
      cancel-text="取消"
      close-on-click-action
      @select="onUploadAction"
    />

    <TabBar />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { showSuccessToast, showFailToast } from 'vant'
import { getUserInfo, getQuota } from '../api/user'
import { getChatUnread } from '../api/chat'
import { getNoticeList, getNoticeDetail } from '../api/notice'
import { getTodos, markPickedUp, submitFeedback } from '../api/application'
import { getPickupReminders, ackPickupReminders } from '../api/notification'
import { useAuthStore } from '../store/auth'
import { isNative } from '../utils/server'
import { unreadCount, setUnread } from '../store/notification'
import TabBar from '../components/TabBar.vue'
import hustRound from '../assets/login/hust-round.png'
import heroImg from '../assets/home/hero.jpg'

// 主视觉背景（CSS 变量注入，避免打包器对内联 url 的处理差异）
document.documentElement.style.setProperty('--home-hero', `url(${heroImg})`)

const router = useRouter()
const auth = useAuthStore()
const user = computed(() => auth.user)
const isAdmin = computed(() => auth.isAdmin)
const remaining = ref(0)
const unread = ref(0)
const noticesLoading = ref(true)

// —— 最新通知：默认折叠几条，点箭头展开全部 ——
const NOTICE_COLLAPSED = 5 // 折叠时展示条数
const NOTICE_EXPANDED = 30 // 展开时最多展示条数（接口最多返回 50 条）
const notices = ref([])
const noticesExpanded = ref(false)
const canExpandNotices = computed(() => notices.value.length > NOTICE_COLLAPSED)
const shownNotices = computed(() =>
  notices.value.slice(0, noticesExpanded.value ? NOTICE_EXPANDED : NOTICE_COLLAPSED),
)

function toggleNotices() {
  noticesExpanded.value = !noticesExpanded.value
}

// —— 公告折叠展开：点开时按需拉取正文并缓存 ——
const activeNotice = ref('') // 当前展开的公告 id（accordion：同时只展开一条）
const noticeContents = ref({}) // id -> 正文

watch(activeNotice, async (id) => {
  if (!id || noticeContents.value[id] != null) return
  try {
    const d = await getNoticeDetail(id)
    noticeContents.value = { ...noticeContents.value, [id]: d?.content || '' }
  } catch (e) {
    noticeContents.value = { ...noticeContents.value, [id]: '正文加载失败，请稍后重试' }
  }
})

// —— 取件提醒弹窗（打印完成 → 首页提示取件）——
const pickupShow = ref(false)
const pickupItems = ref([])
let snoozed = false // 本次进入首页选了「稍后提醒」，就不再自动弹
let pickupTimer = null

// —— 待完成清单（待取件 / 待反馈，像最新通知一样的列表）——
const feedbackShow = ref(false) // 点「提交反馈」图标弹出的列表
const todos = ref([])
const picking = ref(false)
const uploadingId = ref(null)
const fileInput = ref(null)
const cameraInput = ref(null)
const uploadSheetShow = ref(false) // App 内选「拍照 / 相册」
let uploadTarget = null

// App 内才需要选择拍照还是相册；浏览器直接用系统文件选择框
const uploadActions = [
  { name: '拍照上传', key: 'camera' },
  { name: '从相册选择', key: 'gallery' },
]

// 提交反馈图标上的红点数字 = 待反馈条数
const feedbackTodos = computed(() => todos.value.filter((t) => t.kind === 'feedback'))
const feedbackCount = computed(() => feedbackTodos.value.length)
// 弹窗列表沿用待反馈项
const feedbackList = computed(() => feedbackTodos.value)

// 统一待办卡片：管理员 = 汇总行（后端 /todos 返回），学生 = 逐条待办
const ADMIN_ICON = { approve: 'records', print: 'fire-o', chat: 'chat-o', feedback_review: 'photograph' }
const ADMIN_COLOR = { approve: '#2f6bff', print: '#ff976a', chat: '#07c160', feedback_review: '#ff976a' }
const todoItems = computed(() => {
  if (isAdmin.value) {
    return (todos.value || [])
      .map((t) => ({
        ...t,
        // 待回复留言数用轮询的未读数实时更新，其余取后端快照
        count: t.kind === 'chat' ? (unread.value || 0) : t.count,
        icon: ADMIN_ICON[t.kind] || 'records',
        color: ADMIN_COLOR[t.kind] || '#2f6bff',
      }))
      // 数量为 0 的行不显示：没有待办时整张卡片隐藏（无红点）
      .filter((t) => t.kind === 'chat' ? (unread.value || 0) > 0 : (Number(t.count) || 0) > 0)
  }
  return todos.value
})

// 管理后台图标角标 = 真实待办总数（全 0 时无红点）
const todoBadge = computed(() =>
  isAdmin.value ? todoItems.value.reduce((sum, t) => sum + (Number(t.count) || 0), 0) : 0,
)

function todoLabel(t) {
  const file = t.file_name || '模型文件'
  if (t.kind === 'pickup') return `${file} · 打印完成 ${t.completed_at || ''}`
  return t.feedback_deadline ? `${file} · 请在 ${t.feedback_deadline} 前反馈` : file
}

async function loadTodos() {
  try {
    const res = await getTodos()
    todos.value = res?.items || []
  } catch (e) {
    /* 静默失败忽略 */
  }
}

// 「已领取」：标记领取后该条消失
async function onPickupDone(t) {
  picking.value = true
  try {
    await markPickedUp(t.id)
    showSuccessToast('已标记为已领取')
    await loadTodos()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    picking.value = false
  }
}

// 「上传反馈图」：不跳详情页，直接选图/拍照上传到该申请，成功后该条消失
function triggerUpload(t) {
  uploadTarget = t
  try {
    if (isNative()) {
      // App 里让用户选：调用相机拍照，或从相册挑一张
      uploadSheetShow.value = true
      return
    }
    const el = fileInput.value
    if (!el) {
      showFailToast('上传控件未就绪，请刷新页面重试')
      return
    }
    el.click()
  } catch (e) {
    showFailToast('打开文件选择失败，请重试')
  }
}

function onUploadAction(action) {
  // 等 action sheet 收起再唤起相机/相册，否则部分机型会被盖住
  const delay = 260
  const el = action?.key === 'camera' ? cameraInput.value : fileInput.value
  if (!el) {
    showFailToast('当前设备不支持该操作')
    return
  }
  setTimeout(() => el.click(), delay)
}

// 手机拍照通常 3~8MB，后端限制 5MB；上传前压到长边 1600px 的 JPEG
async function shrinkImage(file, maxSide = 1600, quality = 0.82) {
  if (!file || !String(file.type).startsWith('image/')) return file
  try {
    const bitmap = await createImageBitmap(file)
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height))
    if (scale === 1 && file.size <= 3 * 1024 * 1024) return file
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bitmap.width * scale)
    canvas.height = Math.round(bitmap.height * scale)
    canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality))
    bitmap.close?.()
    if (!blob) return file
    const name = `${(file.name || 'feedback').replace(/\.\w+$/, '')}.jpg`
    return new File([blob], name, { type: 'image/jpeg' })
  } catch (e) {
    return file // 压缩失败就原图上传，交给后端校验
  }
}

async function onFilePicked(ev) {
  const raw = ev.target.files?.[0]
  ev.target.value = '' // 允许再次选择同一个文件
  if (!raw || !uploadTarget) return
  const target = uploadTarget
  uploadingId.value = target.id
  try {
    const file = await shrinkImage(raw)
    const fd = new FormData()
    fd.append('file', file, file.name || 'feedback.jpg')
    await submitFeedback(target.id, fd)
    showSuccessToast('反馈已上传，感谢！')
    await loadTodos()
    // 反馈可能奖励打印次数，顺手刷新配额
    getQuota().then((q) => (remaining.value = q.remaining)).catch(() => {})
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    uploadingId.value = null
    uploadTarget = null
  }
}

function openFeedback() {
  feedbackShow.value = true
}

const avatarText = computed(() => (user.value?.name ? user.value.name[0] : '3D'))

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 11) return '上午好'
  if (h < 13) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

onMounted(() => {
  // 并行请求：页面骨架先渲染，数据谁先回来谁先上屏
  getUserInfo()
    .then((info) => {
      auth.setUser(info)
      remaining.value = info.remaining_quota
    })
    .catch(() => {})
  getQuota()
    .then((q) => (remaining.value = q.remaining))
    .catch(() => {})
  getChatUnread(true)
    .then((d) => (unread.value = d.count || 0))
    .catch(() => {})
  getNoticeList()
    .then((list) => (notices.value = list || []))
    .catch(() => {})
    .finally(() => (noticesLoading.value = false))

  // 统一待办接口：管理员返回汇总、学生返回逐条
  loadTodos()

  // 进首页先查一次取件提醒，之后每 30 秒查一次（打印刚完成时无需手动刷新）
  loadPickup()
  pickupTimer = setInterval(() => {
    loadPickup()
    if (!document.hidden && !isAdmin.value) loadTodos()
  }, 30000)

  // 待完成清单（待取件 / 待反馈）：管理员首页不显示
  if (!isAdmin.value) loadTodos()
})

onUnmounted(() => clearInterval(pickupTimer))

// 拉取待确认的取件提醒，有就弹窗
async function loadPickup() {
  if (snoozed || document.hidden || pickupShow.value) return
  try {
    const res = await getPickupReminders()
    if (res && res.count > 0 && res.items?.length) {
      pickupItems.value = res.items
      pickupShow.value = true
    }
  } catch (e) {
    /* 静默失败忽略 */
  }
}

// 稍后提醒：本次不自动弹，下次进首页再提醒（通知仍保持未读）
function snoozePickup() {
  snoozed = true
  pickupShow.value = false
}

// 我知道了：把这些取件提醒标记已读，之后不再弹
async function ackPickup() {
  const ids = pickupItems.value.map((x) => x.id)
  const firstAppId = pickupItems.value[0]?.application?.id
  try {
    const res = await ackPickupReminders(ids)
    if (res && typeof res.count === 'number') setUnread(res.count)
  } catch (e) {
    /* 拦截器已提示 */
  }
  pickupShow.value = false
  pickupItems.value = []
  return firstAppId
}

async function onPickupAck() {
  await ackPickup()
}

async function onPickupView() {
  const appId = await ackPickup()
  if (appId) router.push(`/application/${appId}`)
}
</script>

<style scoped>
/* 主视觉：校园航拍 + 品牌蓝渐变 */
.hero {
  position: relative;
  padding: 32px 20px 56px;
  background-image:
    linear-gradient(118deg, rgba(20, 46, 104, 0.74) 0%, rgba(32, 84, 187, 0.46) 52%, rgba(20, 46, 104, 0.58) 100%),
    var(--home-hero);
  background-size: cover;
  background-position: center 30%;
}
.hero-inner {
  display: flex;
  align-items: center;
  gap: 12px;
}
.avatar {
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  line-height: 48px;
  text-align: center;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.22);
  color: #fff;
  font-size: 20px;
  font-weight: 700;
  border: 1px solid rgba(255, 255, 255, 0.35);
}
.hello {
  min-width: 0;
}
.greet {
  color: #fff;
  font-size: 19px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sub {
  margin-top: 4px;
  color: rgba(255, 255, 255, 0.85);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.hero-badge {
  flex-shrink: 0;
  margin-left: auto;
  width: 46px;
  height: 46px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.92);
  padding: 2px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.18);
}

/* 配额卡片：上浮压住 hero */
.quota-card {
  position: relative;
  z-index: 1;
  margin: -34px 16px 16px;
  padding: 18px 20px;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 6px 20px rgba(20, 46, 104, 0.08);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.quota-label {
  font-size: 13px;
  color: #969799;
}
.quota-num {
  margin-top: 6px;
  font-size: 34px;
  font-weight: 700;
  color: #2f6bff;
  line-height: 1;
}
.quota-num .unit {
  font-size: 13px;
  font-weight: 400;
  color: #969799;
}
.quota-btn {
  flex-shrink: 0;
  padding: 0 18px;
}

/* 待办任务卡（管理员） */
.todo-card {
  margin: 0 16px 16px;
  padding: 14px 16px 6px;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 6px 20px rgba(20, 46, 104, 0.08);
}
.todo-title {
  font-size: 14px;
  font-weight: 600;
  color: #1a2233;
  margin-bottom: 6px;
}
.todo-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 0;
  cursor: pointer;
  border-bottom: 1px solid #f5f6fa;
}
.todo-row > .van-button {
  margin-left: auto;
  flex-shrink: 0;
}
.todo-row:last-child {
  border-bottom: none;
}
.todo-icon {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  background: var(--c, #2f6bff);
  color: #fff;
  font-size: 17px;
}
.todo-label {
  font-size: 14px;
  color: #323233;
}
.todo-count {
  margin-left: auto;
  font-size: 13px;
  font-weight: 700;
  color: #ee0a24;
}
.todo-count.zero {
  color: #969799;
  font-weight: 400;
}

/* 快捷入口：彩色圆角图标 */
.quick-grid {
  margin: 4px 12px 14px;
}
.q-icon {
  width: 46px;
  height: 46px;
  border-radius: 14px;
  display: grid;
  place-items: center;
  background: var(--c, #2f6bff);
  color: #fff;
  font-size: 22px;
  box-shadow: 0 4px 12px color-mix(in srgb, var(--c, #2f6bff) 35%, transparent);
}
.q-text {
  margin-top: 8px;
  font-size: 12px;
  color: #323233;
}

/* 通知 */
.notify-title {
  padding: 4px 20px 8px;
  font-size: 15px;
  font-weight: 600;
  color: #1a2233;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
/* 最新通知：展开/收起箭头（› 旋转 90° 变 ⌄） */
.notify-toggle {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: #2f6bff;
  cursor: pointer;
  transition: transform 0.2s ease, background 0.2s ease;
}
.notify-toggle .van-icon {
  font-size: 14px;
}
.notify-toggle.open {
  transform: rotate(90deg);
}
.notify-toggle:active {
  background: rgba(47, 107, 255, 0.1);
}
.notify-footer {
  margin: 2px 20px 4px;
  padding: 6px 0;
  text-align: center;
  font-size: 12px;
  color: #969799;
  cursor: pointer;
}
.notify-footer:active {
  color: #2f6bff;
}

/* 公告折叠区 */
.notice-box {
  margin: 0 16px;
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
}
.notice-box :deep(.van-collapse-item__title) {
  font-size: 14px;
}
.notice-box :deep(.van-collapse-item__content) {
  padding-top: 0;
  padding-bottom: 14px;
  color: #646566;
  font-size: 13px;
  line-height: 1.75;
}
.notice-text {
  white-space: pre-wrap;
  word-break: break-word;
}
.notice-detail-link {
  margin-top: 8px;
  font-size: 12px;
  color: #2f6bff;
  cursor: pointer;
}

/* 待完成清单 */
.todo-count {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  margin-left: 6px;
  border-radius: 999px;
  background: #ee0a24;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  line-height: 18px;
  text-align: center;
}
.todo-no {
  font-size: 14px;
  color: #323233;
}
.hidden-file {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  overflow: hidden;
  pointer-events: none;
  z-index: -1;
}

/* 取件提醒弹窗 */
.pickup-box {
  padding: 22px 20px 18px;
  text-align: center;
}
.pickup-icon {
  width: 64px;
  height: 64px;
  margin: 0 auto;
  border-radius: 20px;
  display: grid;
  place-items: center;
  color: #fff;
  background: linear-gradient(135deg, #ff976a, #ff6b35);
  box-shadow: 0 8px 20px rgba(255, 107, 53, 0.32);
}
.pickup-title {
  margin-top: 12px;
  font-size: 18px;
  font-weight: 700;
  color: #1a2233;
}
.pickup-sub {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: #969799;
}
.pickup-list {
  margin-top: 14px;
  max-height: 40vh;
  overflow-y: auto;
  text-align: left;
}
.pickup-item {
  padding: 10px 12px;
  border-radius: 10px;
  background: #f7f9ff;
  margin-bottom: 8px;
}
.pickup-item:last-child {
  margin-bottom: 0;
}
.pi-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.pi-no {
  font-size: 14px;
  font-weight: 600;
  color: #2f6bff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pi-file {
  margin-top: 4px;
  font-size: 13px;
  color: #323233;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pi-time {
  margin-top: 2px;
  font-size: 11px;
  color: #969799;
}
.pickup-tip {
  margin: 12px 2px 0;
  font-size: 12px;
  line-height: 1.6;
  color: #969799;
}
.pickup-btns {
  display: flex;
  gap: 12px;
  margin-top: 14px;
}
.pickup-ack {
  margin-top: 12px;
  font-size: 13px;
  color: #969799;
  cursor: pointer;
  padding: 4px 0;
}
.pickup-ack:active {
  color: #2f6bff;
}

/* 待提交反馈弹窗 */
.fb {
  padding: 18px 16px 22px;
}
.fb-title {
  text-align: center;
  font-size: 16px;
  font-weight: 600;
  color: #1a2233;
}
.fb-sub {
  margin: 8px 4px 14px;
  font-size: 12px;
  line-height: 1.6;
  color: #969799;
  text-align: center;
}
.fb-list {
  max-height: 52vh;
  overflow-y: auto;
}
.fb-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 10px;
  background: #f7f9ff;
  margin-bottom: 8px;
}
.fb-item:last-child {
  margin-bottom: 0;
}
.fb-info {
  flex: 1;
  min-width: 0;
}
.fb-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.fb-no {
  font-size: 14px;
  font-weight: 600;
  color: #2f6bff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fb-file {
  margin-top: 4px;
  font-size: 13px;
  color: #323233;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fb-time {
  margin-top: 2px;
  font-size: 11px;
  color: #969799;
}
.fb-deadline {
  margin-top: 2px;
  font-size: 11px;
  color: #ff976a;
}
.fb-btns {
  margin-top: 14px;
}

/* 桌面端：内容撑满 960px 内容列，视觉更舒展 */
@media (min-width: 768px) {
  .hero {
    padding: 56px 36px 76px;
  }
  .greet {
    font-size: 22px;
  }
  .sub {
    font-size: 13px;
  }
  .avatar {
    width: 56px;
    height: 56px;
    line-height: 56px;
    font-size: 24px;
  }
  .hero-badge {
    width: 54px;
    height: 54px;
  }
  .quota-card {
    margin: -52px 36px 20px;
    padding: 24px 28px;
  }
  .quota-num {
    font-size: 40px;
  }
  .quick-grid {
    margin: 8px 24px 18px;
  }
  .q-icon {
    width: 54px;
    height: 54px;
    font-size: 26px;
  }
  .notify-title {
    padding: 6px 36px 10px;
    font-size: 16px;
  }
}
</style>
