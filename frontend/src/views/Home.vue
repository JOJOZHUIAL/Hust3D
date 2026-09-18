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
      <van-grid-item to="/notices">
        <div class="q-icon" style="--c: #ff976a"><van-icon name="question-o" /></div>
        <span class="q-text">使用指南</span>
      </van-grid-item>
      <van-grid-item :to="isAdmin ? '/admin/chat' : '/chat'">
        <div class="q-icon" style="--c: #07c160">
          <van-badge :content="unread > 0 ? String(unread) : undefined" max="99">
            <van-icon name="chat-o" />
          </van-badge>
        </div>
        <span class="q-text">联系工作室</span>
      </van-grid-item>
      <van-grid-item v-if="isAdmin" to="/admin/pending">
        <div class="q-icon" style="--c: #7232dd"><van-icon name="setting-o" /></div>
        <span class="q-text">管理后台</span>
      </van-grid-item>
      <van-grid-item v-else to="/notices">
        <div class="q-icon" style="--c: #969799"><van-icon name="bullhorn-o" /></div>
        <span class="q-text">最新通知</span>
      </van-grid-item>
    </van-grid>

    <!-- 最新通知（取自公告接口，点击查看详情） -->
    <div class="notify-title">
      最新通知
      <span class="notify-more" @click="$router.push('/notices')">全部 ›</span>
    </div>
    <van-cell-group inset>
      <van-cell
        v-for="n in notices"
        :key="n.id"
        :title="n.title"
        :label="`${n.publisher} · ${(n.created_at || '').slice(0, 10)}`"
        is-link
        @click="$router.push({ name: 'notice-detail', params: { id: n.id } })"
      />
      <van-cell v-if="!notices.length && !noticesLoading" title="暂无通知" />
    </van-cell-group>

    <TabBar />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { getUserInfo, getQuota } from '../api/user'
import { getChatUnread } from '../api/chat'
import { getNoticeList } from '../api/notice'
import { useAuthStore } from '../store/auth'
import TabBar from '../components/TabBar.vue'
import hustRound from '../assets/login/hust-round.png'
import heroImg from '../assets/home/hero.jpg'

// 主视觉背景（CSS 变量注入，避免打包器对内联 url 的处理差异）
document.documentElement.style.setProperty('--home-hero', `url(${heroImg})`)

const auth = useAuthStore()
const user = computed(() => auth.user)
const isAdmin = computed(() => auth.isAdmin)
const remaining = ref(0)
const unread = ref(0)
const notices = ref([])
const noticesLoading = ref(true)

const avatarText = computed(() => (user.value?.name ? user.value.name[0] : '3D'))

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 11) return '上午好'
  if (h < 13) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

onMounted(async () => {
  try {
    const info = await getUserInfo()
    auth.setUser(info)
    remaining.value = info.remaining_quota
  } catch (e) {
    /* 拦截器已处理 */
  }
  // 配额单独刷新（顺带触发学期重置逻辑）
  try {
    const q = await getQuota()
    remaining.value = q.remaining
  } catch (e) {
    /* 忽略 */
  }
  // 工作室留言未读数（角标；接口失败静默）
  try {
    unread.value = (await getChatUnread()).count || 0
  } catch (e) {
    /* 忽略 */
  }
  // 最新公告（取前 3 条，点击进详情）
  try {
    notices.value = (await getNoticeList()).slice(0, 3)
  } catch (e) {
    /* 忽略 */
  } finally {
    noticesLoading.value = false
  }
})
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
.notify-more {
  font-size: 12px;
  font-weight: 400;
  color: #2f6bff;
  cursor: pointer;
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
