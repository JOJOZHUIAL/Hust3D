<template>
  <div class="page notices">
    <van-nav-bar title="最新通知" left-arrow fixed placeholder @click-left="$router.back()" />

    <div class="notice-body">
      <van-empty v-if="!loading && list.length === 0" description="暂无通知" />
      <van-cell-group inset>
        <van-cell
          v-for="n in list"
          :key="n.id"
          :title="n.title"
          :label="`${n.publisher} · ${n.created_at}`"
          is-link
          @click="$router.push({ name: 'notice-detail', params: { id: n.id } })"
        />
      </van-cell-group>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getNoticeList } from '../api/notice'

const list = ref([])
const loading = ref(true)

onMounted(async () => {
  try {
    list.value = await getNoticeList()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.notice-body {
  padding-top: 8px;
}
.notice-body :deep(.van-cell__title) {
  white-space: normal;
}
</style>
