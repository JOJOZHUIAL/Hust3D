<template>
  <div class="page admin page--wide">
    <van-nav-bar title="审批管理" left-arrow fixed placeholder @click-left="$router.replace('/admin')" />

    <van-tabs v-model:active="activeTab" sticky @change="load">
      <van-tab title="待审批" name="pending" />
      <van-tab title="全部申请" name="all" />
    </van-tabs>

    <div class="admin-body">
      <van-empty v-if="!loading && list.length === 0" description="暂无数据" />
      <van-card v-for="item in list" :key="item.id" class="admin-card">
        <template #title>{{ item.apply_no }}</template>
        <template #desc>
          <div>{{ item.applicant?.name || '—' }} · {{ item.applicant?.college || '' }}</div>
          <div>{{ PURPOSE_TEXT[item.purpose] || item.purpose }} · {{ item.created_at }}</div>
        </template>
        <template #tags>
          <van-tag :color="STATUS[item.status]?.color">{{ STATUS[item.status]?.text }}</van-tag>
        </template>
        <template #footer>
          <van-button v-if="item.status === 'pending'" size="small" type="primary" @click="onApprove(item)">通过</van-button>
          <van-button v-if="item.status === 'pending'" size="small" type="danger" @click="onReject(item)">拒绝</van-button>
          <van-button v-if="item.status === 'approved'" size="small" type="primary" @click="onAdvance(item, 'printing')">开始打印</van-button>
          <van-button v-if="item.status === 'printing'" size="small" type="success" @click="onAdvance(item, 'completed')">标记完成</van-button>
          <van-button size="small" plain @click="$router.push(`/application/${item.id}`)">详情</van-button>
        </template>
      </van-card>
    </div>

    <!-- 拒绝原因弹窗 -->
    <van-dialog
      v-model:show="rejectShow"
      title="拒绝原因"
      show-cancel-button
      :before-close="beforeRejectClose"
    >
      <van-field
        v-model="rejectComment"
        type="textarea"
        rows="3"
        autosize
        placeholder="请填写拒绝原因"
        class="reject-field"
      />
    </van-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { showConfirmDialog, showSuccessToast, showFailToast } from 'vant'
import { getPendingApplications, getAllApplications, reviewApplication, updateApplicationStatus } from '../../api/admin'
import { STATUS, PURPOSE_TEXT } from '../../utils/constants'
import { readTypeNotifications } from '../../api/notification'
import { setUnread } from '../../store/notification'

const activeTab = ref('pending')
const list = ref([])
const loading = ref(false)

const rejectShow = ref(false)
const rejectComment = ref('')
const rejectTarget = ref(null)

async function load() {
  loading.value = true
  try {
    list.value =
      activeTab.value === 'pending'
        ? await getPendingApplications()
        : await getAllApplications()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

async function onApprove(item) {
  try {
    await showConfirmDialog({ title: '审批确认', message: `确定通过申请 ${item.apply_no} 吗？` })
  } catch (e) {
    return
  }
  try {
    await reviewApplication({ id: item.id, action: 'approve' })
    showSuccessToast('已通过')
    load()
  } catch (e) {
    /* 拦截器已提示 */
  }
}

function onReject(item) {
  rejectTarget.value = item
  rejectComment.value = ''
  rejectShow.value = true
}

// before-close：拒绝原因必填时阻止关闭
function beforeRejectClose(action) {
  if (action === 'confirm') {
    if (!rejectComment.value.trim()) {
      showFailToast('请填写拒绝原因')
      return false
    }
    submitReject()
  }
  return true
}

async function submitReject() {
  try {
    await reviewApplication({ id: rejectTarget.value.id, action: 'reject', comment: rejectComment.value.trim() })
    showSuccessToast('已拒绝')
    load()
  } catch (e) {
    /* 拦截器已提示 */
  }
}

async function onAdvance(item, status) {
  const text = status === 'printing' ? '确定开始打印该申请吗？' : '确定标记为已完成吗？'
  try {
    await showConfirmDialog({ title: '状态更新', message: text })
  } catch (e) {
    return
  }
  try {
    await updateApplicationStatus({ id: item.id, status })
    showSuccessToast('状态已更新')
    load()
  } catch (e) {
    /* 拦截器已提示 */
  }
}

onMounted(() => {
  load()
  readTypeNotifications('apply').then(({ count }) => setUnread(count)).catch(() => {})
})
</script>

<style scoped>
.admin-body {
  padding-top: 8px;
}
.admin-card {
  margin: 8px 16px;
  border-radius: 8px;
}
.reject-field {
  padding: 12px 16px;
}
</style>
