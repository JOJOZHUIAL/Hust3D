// 全局未读通知数（App.vue 轮询更新，TabBar / 首页角标消费）
import { ref } from 'vue'

export const unreadCount = ref(0)

export function setUnread(n) {
  unreadCount.value = Math.max(0, Number(n) || 0)
}
