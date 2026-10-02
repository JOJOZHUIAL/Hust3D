<template>
  <div class="page admin page--wide">
    <van-nav-bar title="留言消息" left-arrow fixed placeholder @click-left="$router.replace('/admin')">
      <template #right>
        <van-icon name="plus" size="20" @click="openContacts" />
      </template>
    </van-nav-bar>

    <div class="conv-body">
      <van-empty v-if="!loading && list.length === 0" description="暂无学生留言，点右上角 + 主动联系学生" />
      <van-cell-group inset>
        <van-cell
          v-for="c in list"
          :key="c.user.id"
          :title="c.user.name || c.user.student_id"
          :label="preview(c.last_message)"
          is-link
          @click="$router.push({ name: 'admin-chat-room', params: { userId: c.user.id } })"
        >
          <template #icon>
            <div class="conv-avatar">{{ (c.user.name || c.user.student_id || '学')[0] }}</div>
          </template>
          <template #value>
            <div class="conv-right">
              <span class="conv-time">{{ shortTime(c.last_message.created_at) }}</span>
              <van-badge v-if="c.unread > 0" :content="c.unread" max="99" />
            </div>
          </template>
        </van-cell>
      </van-cell-group>
    </div>
    <!-- 发起会话：选择学生 -->
    <van-popup v-model:show="showContacts" position="bottom" round :style="{ height: '60%' }">
      <div class="contact-panel">
        <van-search v-model="searchKey" placeholder="搜索姓名 / 学号" shape="round" />
        <div class="contact-list">
          <van-cell
            v-for="u in filteredContacts"
            :key="u.id"
            :title="u.name || u.student_id"
            :label="`${u.student_id || ''} · ${u.college || ''}`"
            is-link
            @click="goRoom(u)"
          >
            <template #icon>
              <div class="conv-avatar">{{ (u.name || u.student_id || '学')[0] }}</div>
            </template>
          </van-cell>
          <van-empty v-if="filteredContacts.length === 0" description="没有匹配的学生" />
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { getChatConversations, getChatContacts } from '../../api/chat'

const router = useRouter()
const list = ref([])
const loading = ref(true)
let pollTimer = null

// 发起会话弹层
const showContacts = ref(false)
const contacts = ref([])
const searchKey = ref('')
const filteredContacts = computed(() => {
  const k = searchKey.value.trim()
  if (!k) return contacts.value
  return contacts.value.filter(
    (u) => (u.name || '').includes(k) || (u.student_id || '').includes(k),
  )
})

async function openContacts() {
  showContacts.value = true
  try {
    contacts.value = await getChatContacts()
  } catch (e) {
    /* 拦截器已提示 */
  }
}

function goRoom(u) {
  showContacts.value = false
  router.push({ name: 'admin-chat-room', params: { userId: u.id } })
}

// 会话预览：文字直接显示，其他类型显示类型标签
function preview(m) {
  const who = m.sender_role === 'user' ? '' : '【工作室】'
  const tag = { image: '[图片]', video: '[视频]', voice: '[语音]', file: '[文件]' }[m.content_type]
  return who + (m.content_type === 'text' ? m.content || '' : tag)
}

function shortTime(s) {
  if (!s) return ''
  return s.slice(5, 16).replace('T', ' ')
}

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    list.value = await getChatConversations(silent)
  } catch (e) {
    /* 静默轮询失败不打扰 */
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  load()
  pollTimer = setInterval(() => {
    if (!document.hidden) load(true)
  }, 6000)
})

onUnmounted(() => clearInterval(pollTimer))
</script>

<style scoped>
.conv-body {
  padding-top: 8px;
}
.conv-avatar {
  width: 40px;
  height: 40px;
  margin-right: 10px;
  line-height: 40px;
  text-align: center;
  border-radius: 50%;
  background: #dbe4ff;
  color: #2f6bff;
  font-weight: 600;
}
.conv-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}
.conv-time {
  font-size: 11px;
  color: #c8c9cc;
}
.contact-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.contact-list {
  flex: 1;
  overflow-y: auto;
}
</style>
