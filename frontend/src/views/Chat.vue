<template>
  <div class="page chat">
    <van-nav-bar
      :title="navTitle"
      left-arrow
      fixed
      placeholder
      @click-left="$router.back()"
    />

    <!-- 消息列表 -->
    <div ref="listEl" class="msgs" @scroll="onScroll">
      <van-loading v-if="loading" style="margin: 24px auto" size="24" vertical>加载中...</van-loading>
      <van-empty
        v-else-if="messages.length === 0"
        description="暂无消息，向工作室发起咨询吧"
        style="margin-top: 40px"
      />
      <template v-for="(m, i) in messages" :key="m.id">
        <div v-if="showDivider(i)" class="time-divider">{{ fmtTime(m.created_at) }}</div>
        <div class="msg-row" :class="{ mine: isMine(m) }">
          <div class="avatar">{{ avatarText(m) }}</div>
          <div class="bubble" :class="'type-' + m.content_type">
            <!-- 文字/表情 -->
            <template v-if="m.content_type === 'text'">
              <div class="txt">{{ m.content }}</div>
            </template>
            <!-- 图片 -->
            <img
              v-else-if="m.content_type === 'image'"
              :src="assetUrl(m.file_url)"
              class="pic"
              alt="图片"
              @click="previewImage(m)"
            />
            <!-- 视频 -->
            <video
              v-else-if="m.content_type === 'video'"
              :src="assetUrl(m.file_url)"
              controls
              preload="metadata"
              class="video"
            ></video>
            <!-- 语音 -->
            <div
              v-else-if="m.content_type === 'voice'"
              class="voice"
              @click="toggleVoice(m)"
            >
              <van-icon :name="playingId === m.id ? 'volume-o' : 'play-circle-o'" size="20" />
              <span class="voice-sec">{{ m.duration || 0 }}"</span>
              <span v-if="playingId === m.id" class="voice-tip">播放中</span>
            </div>
            <!-- 文件 -->
            <div v-else class="file" @click="downloadFile(m)">
              <van-icon name="description-o" size="26" />
              <div class="file-info">
                <div class="file-name">{{ m.file_name }}</div>
                <div class="file-size">{{ fmtSize(m.file_size) }} · 点击下载</div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 输入区 -->
    <div class="input-bar">
      <!-- 语音模式：按住说话 -->
      <template v-if="voiceMode">
        <van-icon name="edit" size="24" class="bar-icon" @click="toggleVoiceMode" />
        <button
          class="hold-btn"
          :class="{ rec: recording }"
          type="button"
          @pointerdown.prevent="holdStart"
          @pointerup.prevent="holdEnd"
          @pointerleave="holdCancel"
          @contextmenu.prevent
          @dragstart.prevent
        >
          {{ recording ? `松开发送 ${recSeconds}s` : micStarting ? '请稍候…' : '按住 说话' }}
        </button>
        <van-icon name="smile-o" size="24" class="bar-icon" @click="showEmoji = true" />
        <van-icon name="plus" size="24" class="bar-icon" @click="showAttach = true" />
      </template>
      <!-- 常规输入 -->
      <template v-else>
        <van-icon name="audio" size="24" class="bar-icon" @click="toggleVoiceMode" />
        <van-field
          v-model="inputText"
          class="input-field"
          rows="1"
          autosize
          type="textarea"
          maxlength="2000"
          placeholder="输入消息…"
          @keydown.enter.exact.prevent="sendText"
        />
        <van-icon name="smile-o" size="24" class="bar-icon" @click="showEmoji = true" />
        <van-icon name="plus" size="24" class="bar-icon" @click="showAttach = true" />
        <van-button
          type="primary"
          size="small"
          round
          :disabled="!inputText.trim()"
          :loading="sending"
          @click="sendText"
        >
          发送
        </van-button>
      </template>
    </div>

    <!-- 表情选择 -->
    <van-popup v-model:show="showEmoji" position="bottom" round :style="{ height: '38%' }">
      <div class="emoji-panel">
        <div class="emoji-grid">
          <button
            v-for="e in EMOJIS"
            :key="e"
            type="button"
            class="emoji-item"
            @click="inputText += e"
          >
            {{ e }}
          </button>
        </div>
        <van-button type="primary" size="small" block round @click="showEmoji = false">
          关闭
        </van-button>
      </div>
    </van-popup>

    <!-- 附件选择 -->
    <van-action-sheet
      v-model:show="showAttach"
      :actions="[
        { name: '图片', icon: 'photo-o' },
        { name: '视频', icon: 'video-o' },
        { name: '文件', icon: 'description-o' },
      ]"
      cancel-text="取消"
      @select="onAttachSelect"
    />
    <input ref="imgInput" type="file" accept="image/*" hidden @change="e => onPickFile(e, 'image')" />
    <input ref="videoInput" type="file" accept="video/*" hidden @change="e => onPickFile(e, 'video')" />
    <input ref="fileInput" type="file" hidden @change="e => onPickFile(e, 'file')" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showFailToast, showImagePreview } from 'vant'
import { sendChatMessage, getChatMessages } from '../api/chat'
import { downloadBlob } from '../api/application'
import { useAuthStore } from '../store/auth'
import { assetUrl as serverAssetUrl } from '../utils/server'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

// 管理员模式：/admin/chat/:userId 复用本组件回复学生
const adminMode = computed(() => route.name === 'admin-chat-room')
const peerId = computed(() => Number(route.params.userId))

const loading = ref(true)
const messages = ref([])
const peer = ref(null)
const inputText = ref('')
const sending = ref(false)
const voiceMode = ref(false)
const showEmoji = ref(false)
const showAttach = ref(false)

const imgInput = ref(null)
const videoInput = ref(null)
const fileInput = ref(null)

const listEl = ref(null)

// —— 表情（内置常用 emoji，无需外部依赖） ——
const EMOJIS = [
  '😀', '😄', '😁', '😆', '😅', '🤣', '😂', '🙂', '😉', '😊', '😍', '🥰',
  '😘', '😜', '🤪', '🤗', '🤔', '😐', '😴', '🥺', '😢', '😭', '😤', '😠',
  '🤯', '😱', '🥳', '😎', '🤓', '🙄', '😇', '🙏', '👍', '👎', '👌', '✌️',
  '🤝', '👏', '💪', '🫶', '❤️', '💔', '✨', '🔥', '🎉', '🎁', '🌹', '🌸',
  '☕', '🍺', '🍕', '⚽', '🚀', '💡', '📢', '💬', '📝', '📌', '✅', '❌',
]

const navTitle = computed(() => {
  if (adminMode.value) return peer.value?.name || '会话'
  return '联系工作室'
})

function isMine(m) {
  return adminMode.value ? m.sender_role === 'admin' : m.sender_role === 'user'
}
function avatarText(m) {
  if (isMine(m)) return adminMode.value ? '工' : (auth.user?.name?.[0] || '学')
  return adminMode.value ? (peer.value?.name?.[0] || '学') : '工'
}

// App 模式下资源指向服务器（utils/server 统一处理）
const assetUrl = serverAssetUrl

function fmtSize(n) {
  if (!n && n !== 0) return ''
  if (n < 1024) return n + 'B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + 'KB'
  return (n / 1024 / 1024).toFixed(1) + 'MB'
}

function fmtTime(s) {
  if (!s) return ''
  const d = new Date(s.replace('-', '/').replace('-', '/'))
  const now = new Date()
  const hm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  if (d.toDateString() === now.toDateString()) return hm
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${hm}`
}

// 与上一条间隔超过 3 分钟时显示时间分隔
function showDivider(i) {
  if (i === 0) return true
  const prev = new Date(messages.value[i - 1].created_at.replace('-', '/').replace('-', '/'))
  const cur = new Date(messages.value[i].created_at.replace('-', '/').replace('-', '/'))
  return cur - prev > 3 * 60 * 1000
}

// —— 消息加载与轮询 ——
let pollTimer = null

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    const params = adminMode.value ? { user_id: peerId.value } : {}
    const data = await getChatMessages(params, silent)
    if (adminMode.value) peer.value = data.peer
    const pinned = isNearBottom()
    messages.value = data.messages || []
    if (pinned) scrollToBottom()
  } catch (e) {
    /* 静默轮询失败不打扰；首次加载由拦截器提示 */
  } finally {
    loading.value = false
  }
}

function isNearBottom() {
  const el = listEl.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight < 80
}

function scrollToBottom() {
  nextTick(() => {
    const el = listEl.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

function onScroll() { /* 预留：上滑加载更多 */ }

// —— 发送 ——
function baseForm() {
  const fd = new FormData()
  if (adminMode.value) fd.append('user_id', String(peerId.value))
  return fd
}

async function sendText() {
  const text = inputText.value.trim()
  if (!text || sending.value) return
  const fd = baseForm()
  fd.append('content_type', 'text')
  fd.append('content', text)
  sending.value = true
  try {
    const msg = await sendChatMessage(fd)
    messages.value.push(msg)
    inputText.value = ''
    scrollToBottom()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    sending.value = false
  }
}

async function sendMedia(type, file, duration = null) {
  const fd = baseForm()
  fd.append('content_type', type)
  fd.append('file', file)
  if (duration !== null) fd.append('duration', String(duration))
  sending.value = true
  try {
    const msg = await sendChatMessage(fd)
    messages.value.push(msg)
    scrollToBottom()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    sending.value = false
  }
}

function onAttachSelect(action) {
  showAttach.value = false
  nextTick(() => {
    if (action.name === '图片') imgInput.value?.click()
    else if (action.name === '视频') videoInput.value?.click()
    else fileInput.value?.click()
  })
}

const SIZE_LIMIT = { image: 10 * 1024 * 1024, video: 50 * 1024 * 1024, file: 50 * 1024 * 1024 }

function onPickFile(e, type) {
  const f = e.target.files[0]
  e.target.value = ''
  if (!f) return
  if (f.size > SIZE_LIMIT[type]) {
    showFailToast(`文件不能超过 ${SIZE_LIMIT[type] / 1024 / 1024}MB`)
    return
  }
  sendMedia(type, f)
}

// —— 图片预览 / 文件下载 / 语音播放 ——
function previewImage(m) {
  // 注意：Vant 的 showImagePreview(数组, 对象) 会把对象当 startPosition 解析出 NaN，
  // 必须用单对象参数才能让 closeable（右上角关闭按钮）生效
  showImagePreview({ images: [assetUrl(m.file_url)], closeable: true, closeOnPopstate: true })
}

// 文件下载：fetch 取回内容后以原始文件名另存，
// 避免 window.open 被内嵌浏览器拦截，也避免 .md/.txt 等被直接“打开显示”
async function downloadFile(m) {
  try {
    const res = await fetch(assetUrl(m.file_url))
    if (!res.ok) throw new Error('HTTP ' + res.status)
    downloadBlob(await res.blob(), m.file_name || '文件')
  } catch (e) {
    showFailToast('下载失败，请重试')
  }
}

let audio = null
let audioUrl = ''
const playingId = ref(0)
const loadingVoiceId = ref(0)

// 语音扩展名 → 播放用 MIME
const VOICE_MIME = {
  webm: 'audio/webm',
  m4a: 'audio/mp4',
  mp4: 'audio/mp4',
  ogg: 'audio/ogg',
  opus: 'audio/ogg',
  mp3: 'audio/mpeg',
  wav: 'audio/wav',
  aac: 'audio/aac',
}

async function toggleVoice(m) {
  if (playingId.value === m.id) {
    audio?.pause()
    playingId.value = 0
    return
  }
  if (loadingVoiceId.value) return
  loadingVoiceId.value = m.id
  try {
    // 先取回字节，按扩展名给出准确类型后交给 <audio>，
    // 规避服务器 MIME（webm→video/webm）或 Safari 录音（m4a）导致的加载失败
    const res = await fetch(assetUrl(m.file_url))
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const ext = ((m.file_name || m.file_url || '').split('.').pop() || '').toLowerCase()
    const mime = VOICE_MIME[ext] || 'audio/webm'
    const blob = new Blob([await res.arrayBuffer()], { type: mime })
    audio?.pause()
    if (audioUrl) URL.revokeObjectURL(audioUrl)
    audioUrl = URL.createObjectURL(blob)
    audio = new Audio(audioUrl)
    audio.onended = () => (playingId.value = 0)
    await audio.play()
    playingId.value = m.id
  } catch (e) {
    showFailToast('语音播放失败，请重试')
  } finally {
    loadingVoiceId.value = 0
  }
}

// —— 语音录制（MediaRecorder，按住说话：松开发送，按住时移出按钮取消） ——
const recording = ref(false)
const micStarting = ref(false) // 麦克风授权/开启中（尚未真正开始录音）
const recSeconds = ref(0)
let mediaRecorder = null
let mediaStream = null
let recChunks = []
let recTimer = null
let recCancelled = false
let recCancelReason = null // 'leave'=移出取消 | 'tap'=松开过早
let recStartAt = 0
let recWantsStop = false // 录音尚未开始就松开了 → 开始后立即丢弃

function toggleVoiceMode() {
  if (recording.value) stopRec(true) // 切回键盘时丢弃未完成的录音
  voiceMode.value = !voiceMode.value
}

async function holdStart() {
  if (recording.value || micStarting.value) return
  recWantsStop = false
  micStarting.value = true
  try {
    await startRec()
  } finally {
    micStarting.value = false
  }
}

function holdEnd() {
  if (recording.value) {
    stopRec(false) // 松开 → 发送
  } else if (micStarting.value) {
    // 麦克风还没就绪就松开了（快速点按）→ 开启后直接丢弃
    recWantsStop = true
    recCancelReason = 'tap'
  }
}

function holdCancel() {
  if (!recording.value) return
  recCancelReason = 'leave'
  stopRec(true) // 按住后移出按钮 → 取消
}

async function startRec() {
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
    showFailToast('当前浏览器不支持录音')
    return
  }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch (e) {
    showFailToast('无法访问麦克风，请检查权限')
    return
  }
  recChunks = []
  recCancelled = false
  const mime = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm'
    : MediaRecorder.isTypeSupported('audio/mp4') ? 'audio/mp4' : ''
  mediaRecorder = new MediaRecorder(mediaStream, mime ? { mimeType: mime } : undefined)
  mediaRecorder.ondataavailable = (e) => {
    if (e.data && e.data.size) recChunks.push(e.data)
  }
  mediaRecorder.onstop = onRecStop
  mediaRecorder.start()
  recSeconds.value = 0
  recStartAt = Date.now()
  recording.value = true
  recTimer = setInterval(() => {
    recSeconds.value = Math.floor((Date.now() - recStartAt) / 1000)
    if (recSeconds.value >= 60) stopRec(false) // 最长 60 秒自动发送
  }, 1000)
  if (recWantsStop) {
    recWantsStop = false
    stopRec(true)
  }
}

function stopRec(cancel) {
  recCancelled = cancel
  clearInterval(recTimer)
  if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop()
}

function onRecStop() {
  recording.value = false
  mediaStream?.getTracks().forEach((t) => t.stop())
  mediaStream = null
  const seconds = Math.max(1, Math.round((Date.now() - recStartAt) / 1000))
  // 取消（移出按钮）或过早松开：丢弃且不发
  if (recCancelled) {
    showFailToast(recCancelReason === 'tap' ? '说话时间太短，请按住说话' : '已取消')
    recCancelReason = null
    return
  }
  // 只有文件头的空录音（<1KB）同样视为太短
  const blob = new Blob(recChunks, { type: mediaRecorder?.mimeType || 'audio/webm' })
  if (seconds < 1 || blob.size < 1000) {
    showFailToast('说话时间太短，请重试')
    return
  }
  if (blob.size > 10 * 1024 * 1024) {
    showFailToast('录音不能超过 10MB')
    return
  }
  const type = mediaRecorder?.mimeType || 'audio/webm'
  const ext = type.includes('mp4') ? 'm4a' : type.includes('ogg') ? 'ogg' : 'webm'
  sendMedia('voice', new File([blob], `voice.${ext}`, { type }), seconds)
}

onMounted(() => {
  // 管理员没有「自己」的学生会话，误入 /chat 时转跳到会话列表
  if (!adminMode.value && auth.isAdmin) {
    router.replace({ name: 'admin-chat' })
    return
  }
  load()
  // 轮询刷新（页面隐藏时跳过，销毁时清理）
  pollTimer = setInterval(() => {
    if (!document.hidden && !sending.value && !recording.value) load(true)
  }, 4000)
})

onUnmounted(() => {
  clearInterval(pollTimer)
  audio?.pause()
  if (mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop()
  mediaStream?.getTracks().forEach((t) => t.stop())
  clearInterval(recTimer)
})
</script>

<style scoped>
.chat {
  height: 100vh;
  display: flex;
  flex-direction: column;
  padding-bottom: 0;
  overflow: hidden;
}
.msgs {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0 12px;
}
.time-divider {
  margin: 12px 0 4px;
  text-align: center;
  font-size: 11px;
  color: #969799;
}
.msg-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 8px 12px;
}
.msg-row.mine {
  flex-direction: row-reverse;
}
.avatar {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  line-height: 36px;
  text-align: center;
  border-radius: 50%;
  background: #dbe4ff;
  color: #2f6bff;
  font-size: 14px;
  font-weight: 600;
}
.msg-row.mine .avatar {
  background: #2f6bff;
  color: #fff;
}
.bubble {
  max-width: 70%;
  padding: 8px 12px;
  border-radius: 4px 12px 12px 12px;
  background: #fff;
  font-size: 14px;
  color: #323233;
  word-break: break-word;
}
.msg-row.mine .bubble {
  border-radius: 12px 4px 12px 12px;
  background: #2f6bff;
  color: #fff;
}
.bubble .txt {
  white-space: pre-wrap;
  line-height: 1.5;
}
.pic {
  display: block;
  max-width: 180px;
  max-height: 240px;
  border-radius: 6px;
  cursor: pointer;
}
.video {
  display: block;
  max-width: 200px;
  border-radius: 6px;
}
.voice {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 90px;
  cursor: pointer;
}
.voice-sec {
  font-size: 14px;
}
.voice-tip {
  font-size: 11px;
  opacity: 0.8;
}
.file {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 160px;
  max-width: 220px;
  cursor: pointer;
}
.file-info {
  min-width: 0;
}
.file-name {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-size {
  margin-top: 2px;
  font-size: 11px;
  opacity: 0.7;
}

/* 输入区 */
.input-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px calc(8px + constant(safe-area-inset-bottom));
  padding-bottom: calc(8px + env(safe-area-inset-bottom));
  background: #fff;
  border-top: 1px solid #ebedf0;
}
.bar-icon {
  flex-shrink: 0;
  color: #646566;
  cursor: pointer;
}
.input-field {
  flex: 1;
  padding: 6px 10px;
  background: #f7f8fa;
  border-radius: 8px;
}
.voice-entry {
  flex: 1;
  padding: 8px 10px;
  text-align: center;
  background: #f7f8fa;
  border: none;
  border-radius: 8px;
  color: #2f6bff;
  font-size: 14px;
  cursor: pointer;
}
/* 按住说话按钮：松开发送、移出取消 */
.hold-btn {
  flex: 1;
  padding: 9px 10px;
  border: none;
  border-radius: 8px;
  background: #f7f8fa;
  color: #2f6bff;
  font-size: 14px;
  cursor: pointer;
  user-select: none;
  -webkit-user-select: none;
  -webkit-touch-callout: none;
  touch-action: none;
}
.hold-btn.rec {
  background: #ee0a24;
  color: #fff;
  font-weight: 600;
}

/* 表情面板 */
.emoji-panel {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
}
.emoji-grid {
  flex: 1;
  overflow-y: auto;
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 4px;
}
.emoji-item {
  border: none;
  background: none;
  font-size: 26px;
  line-height: 1.4;
  cursor: pointer;
}
.emoji-item:active {
  background: #f2f3f5;
  border-radius: 6px;
}
</style>
