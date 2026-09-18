<template>
  <div class="page notice-detail">
    <van-nav-bar title="通知详情" left-arrow fixed placeholder @click-left="$router.back()" />

    <van-skeleton v-if="loading" title :row="6" style="margin-top: 16px" />

    <van-empty v-else-if="!notice" description="公告不存在" />

    <template v-else>
      <div class="detail-card">
        <h1 class="d-title">{{ notice.title }}</h1>
        <div class="d-meta">
          <span>{{ notice.publisher }}</span>
          <span>{{ (notice.updated_at || notice.created_at || '').slice(0, 16) }}</span>
        </div>
        <div class="d-divider"></div>
        <div class="d-content">{{ notice.content }}</div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getNoticeDetail } from '../api/notice'

const route = useRoute()
const notice = ref(null)
const loading = ref(true)

onMounted(async () => {
  try {
    notice.value = await getNoticeDetail(route.params.id)
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.detail-card {
  margin: 12px 16px;
  padding: 22px 20px;
  border-radius: 12px;
  background: #fff;
}
.d-title {
  margin: 0;
  font-size: 19px;
  line-height: 1.45;
  color: #1a2233;
}
.d-meta {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-top: 12px;
  font-size: 12px;
  color: #969799;
}
.d-divider {
  height: 1px;
  background: #f0f1f5;
  margin: 14px 0;
}
.d-content {
  font-size: 15px;
  line-height: 1.9;
  color: #323233;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
