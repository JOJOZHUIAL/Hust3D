<template>
  <div class="page notifications">
    <van-nav-bar title="消息中心" left-arrow fixed placeholder @click-left="goBack">
      <template #right>
        <span v-if="list.length" class="read-all" @click="onReadAll">全部已读</span>
      </template>
    </van-nav-bar>

    <van-empty v-if="!loading && list.length === 0" description="暂无消息" />

    <van-cell-group v-else inset style="margin-top: 10px">
      <van-cell
        v-for="n in list"
        :key="n.id"
        :label="n.body || ''"
        is-link
        :class="{ unread: !n.is_read }"
        @click="onItemClick(n)"
      >
        <template #title>
          <span class="n-title">
            <span v-if="!n.is_read" class="n-dot"></span>
            {{ n.title }}
          </span>
        </template>
        <template #value>
          <span class="n-time">{{ (n.created_at || '').slice(5, 16) }}</span>
        </template>
      </van-cell>
    </van-cell-group>

    <TabBar />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  getNotificationList, readNotification, readAllNotifications,
} from '../api/notification'
import { setUnread } from '../store/notification'
import TabBar from '../components/TabBar.vue'

const router = useRouter()

function goBack() {
  if (window.history.length > 1) router.back()
  else router.replace('/')
}

const list = ref([])
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    list.value = await getNotificationList()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

const TYPE_ICON = { approval: '审批', apply: '申请', chat: '留言', consumable: '耗材' }

async function onItemClick(n) {
  if (!n.is_read) {
    n.is_read = true
    try { await readNotification(n.id) } catch (e) { /* 忽略 */ }
    const remain = Math.max(0, list.value.filter((x) => !x.is_read).length)
    setUnread(remain)
  }
  if (n.link) router.push(n.link)
}

async function onReadAll() {
  try {
    await readAllNotifications()
    list.value.forEach((n) => (n.is_read = true))
    setUnread(0)
    // 同步清掉 App 的系统通知横幅
    window.__clearAppBadge?.()
  } catch (e) {
    /* 拦截器已提示 */
  }
}

onMounted(load)
</script>

<style scoped>
.read-all {
  font-size: 13px;
  color: #2f6bff;
  cursor: pointer;
}
.n-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  color: #323233;
  white-space: normal;
}
.unread .n-title {
  font-weight: 600;
}
.n-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ee0a24;
}
.n-time {
  font-size: 11px;
  color: #c8c9cc;
}
</style>
