<template>
  <div class="page admin-home">
    <van-nav-bar title="管理后台" left-arrow fixed placeholder @click-left="$router.back()" />

    <div class="hub-greeting">
      <div class="hello">{{ user?.name || '管理员' }}，今天也辛苦了</div>
      <div class="sub">点击下方图标进入各子服务</div>
    </div>

    <div class="hub-grid">
      <div class="hub-item" @click="$router.push('/admin/pending')">
        <van-badge :content="pendingCount > 0 ? String(pendingCount) : undefined" max="99">
          <div class="hub-icon" style="--c: #2f6bff"><van-icon name="records" /></div>
        </van-badge>
        <div class="hub-name">审批管理</div>
        <div class="hub-desc">打印申请审批与状态推进</div>
      </div>

      <div class="hub-item" @click="$router.push('/admin/notices')">
        <div class="hub-icon" style="--c: #ff976a"><van-icon name="bullhorn-o" /></div>
        <div class="hub-name">公告管理</div>
        <div class="hub-desc">发布与维护最新通知</div>
      </div>

      <div class="hub-item" @click="$router.push('/admin/chat')">
        <van-badge :content="chatUnread > 0 ? String(chatUnread) : undefined" max="99">
          <div class="hub-icon" style="--c: #07c160"><van-icon name="chat-o" /></div>
        </van-badge>
        <div class="hub-name">联系留言</div>
        <div class="hub-desc">回复学生咨询与留言</div>
      </div>

      <div v-if="isSuper" class="hub-item" @click="$router.push('/admin/admins')">
        <div class="hub-icon" style="--c: #ee0a24"><van-icon name="manager-o" /></div>
        <div class="hub-name">管理员管理</div>
        <div class="hub-desc">添加与移除管理员</div>
      </div>

      <div class="hub-item" @click="$router.push('/admin/consumables')">
        <div class="hub-icon" style="--c: #7232dd"><van-icon name="scan" /></div>
        <div class="hub-name">耗材管理</div>
        <div class="hub-desc">扫码登记耗材入库与拆封</div>
      </div>
    </div>

    <TabBar />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '../../store/auth'
import { getPendingApplications } from '../../api/admin'
import { getChatUnread } from '../../api/chat'
import TabBar from '../../components/TabBar.vue'

const auth = useAuthStore()
const user = computed(() => auth.user)
const isSuper = computed(() => auth.user?.role === 'superadmin')
const pendingCount = ref(0)
const chatUnread = ref(0)

onMounted(async () => {
  // 待审批数（角标）
  try {
    pendingCount.value = (await getPendingApplications()).length
  } catch (e) {
    /* 忽略 */
  }
  // 学生留言未读数（角标）
  try {
    chatUnread.value = (await getChatUnread(true)).count || 0
  } catch (e) {
    /* 忽略 */
  }
})
</script>

<style scoped>
.hub-greeting {
  padding: 26px 20px 10px;
}
.hello {
  font-size: 20px;
  font-weight: 600;
  color: #1a2233;
}
.sub {
  margin-top: 6px;
  font-size: 13px;
  color: #969799;
}
.hub-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
  padding: 14px 16px 24px;
}
.hub-item {
  background: #fff;
  border-radius: 16px;
  padding: 22px 16px 18px;
  text-align: center;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(20, 46, 104, 0.06);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.hub-item:active {
  transform: scale(0.96);
  box-shadow: 0 2px 8px rgba(20, 46, 104, 0.1);
}
.hub-icon {
  width: 58px;
  height: 58px;
  margin: 0 auto;
  border-radius: 18px;
  display: grid;
  place-items: center;
  background: var(--c, #2f6bff);
  color: #fff;
  font-size: 28px;
  box-shadow: 0 6px 16px color-mix(in srgb, var(--c, #2f6bff) 35%, transparent);
}
.hub-name {
  margin-top: 12px;
  font-size: 15px;
  font-weight: 600;
  color: #1a2233;
}
.hub-desc {
  margin-top: 4px;
  font-size: 11px;
  color: #969799;
}

/* 桌面端：图标卡更大更舒展 */
@media (min-width: 768px) {
  .hub-grid {
    grid-template-columns: repeat(4, 1fr);
    padding: 20px 36px 32px;
  }
  .hub-greeting {
    padding: 36px 36px 12px;
  }
}
</style>
