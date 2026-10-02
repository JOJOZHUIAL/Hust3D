<template>
  <div class="page list">
    <van-nav-bar title="我的申请" left-arrow fixed placeholder @click-left="$router.back()" />

    <van-tabs v-model:active="activeTab" sticky @change="onTabChange">
      <van-tab v-for="t in TABS" :key="t.value" :title="t.label" :name="t.value" />
    </van-tabs>

    <div class="list-body">
      <van-empty v-if="!loading && list.length === 0" description="暂无申请记录" />
      <van-cell-group v-else inset>
        <van-cell
          v-for="item in list"
          :key="item.id"
          :title="item.apply_no"
          :label="`${PURPOSE_TEXT[item.purpose] || item.purpose} · ${item.created_at}`"
          is-link
          @click="$router.push(`/application/${item.id}`)"
        >
          <template #value>
            <van-tag :color="STATUS[item.status]?.color">{{ STATUS[item.status]?.text }}</van-tag>
            <van-tag v-if="item.feedback_url" color="#07c160">已反馈</van-tag>
            <van-tag v-else-if="item.status === 'completed'" color="#ff976a">未反馈</van-tag>
          </template>
        </van-cell>
      </van-cell-group>
    </div>

    <TabBar />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getMyApplications } from '../api/application'
import TabBar from '../components/TabBar.vue'
import { STATUS, PURPOSE_TEXT } from '../utils/constants'

const TABS = [
  { value: '', label: '全部' },
  { value: 'pending', label: '待审批' },
  { value: 'approved', label: '已通过' },
  { value: 'printing', label: '打印中' },
  { value: 'completed', label: '已完成' },
  { value: 'rejected', label: '已拒绝' },
  { value: 'cancelled', label: '已取消' },
]

const activeTab = ref('')
const list = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const params = activeTab.value ? { status: activeTab.value } : {}
    list.value = await getMyApplications(params)
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

function onTabChange() {
  load()
}

onMounted(load)
</script>

<style scoped>
.list-body {
  padding-top: 8px;
}
</style>
