<template>
  <div class="page admin page--wide">
    <van-nav-bar title="审批管理" left-arrow fixed placeholder @click-left="$router.replace('/admin')" />

    <!-- 分组筛选 chips（自动换行，无需横向拖拽） -->
    <div class="chips">
      <button
        v-for="c in cats"
        :key="c.key"
        class="chip"
        :class="{ active: active === c.key }"
        type="button"
        @click="active = c.key"
      >
        {{ c.label }}
        <span v-if="c.count" class="chip-count">{{ c.count }}</span>
      </button>
    </div>

    <div class="admin-body">
      <van-empty v-if="!loading && shown.length === 0" :description="`「${activeLabel}」暂无申请`" />
      <van-card v-for="item in shown" :key="item.id" class="admin-card">
        <template #title>
          {{ item.apply_no }}
          <van-tag v-if="item.feedback_url && item.feedback_reviewed === false" color="#ffd21e" text-color="#ad6800" style="margin-left: 6px">
            反馈待审核
          </van-tag>
        </template>
        <template #desc>
          <div>{{ item.applicant?.name || '—' }} · {{ item.applicant?.college || '' }}</div>
          <div>{{ PURPOSE_TEXT[item.purpose] || item.purpose }} · {{ item.created_at }}</div>
        </template>
        <template #tags>
          <van-tag :color="STATUS[item.status]?.color">{{ STATUS[item.status]?.text }}</van-tag>
          <van-tag v-if="item.feedback_url && item.feedback_reviewed !== 2" color="#07c160">已反馈</van-tag>
        </template>
        <template #footer>
          <van-button v-if="item.status === 'pending'" size="small" type="primary" @click="onApprove(item)">通过</van-button>
          <van-button v-if="item.status === 'pending'" size="small" type="danger" @click="onReject(item)">拒绝</van-button>
          <van-button v-if="item.status === 'approved'" size="small" type="primary" @click="onAdvance(item, 'printing')">开始打印</van-button>
          <van-button v-if="item.status === 'printing'" size="small" type="success" @click="onAdvance(item, 'completed')">标记完成</van-button>
          <!-- 反馈审核（FEEDBACK_REWARD_MODE=review 时） -->
          <template v-if="item.feedback_url && item.feedback_reviewed === false">
            <van-button size="small" type="success" @click="openReview(item)">反馈通过</van-button>
            <van-button size="small" plain type="danger" @click="onReview(item, 'reject')">反馈拒绝</van-button>
          </template>
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

    <!-- 反馈通过：自选奖励次数 -->
    <van-dialog
      v-model:show="reviewShow"
      title="反馈通过"
      show-cancel-button
      :before-close="beforeReviewClose"
    >
      <div class="review-box">
        <div class="review-item">{{ reviewTarget?.apply_no }}</div>
        <van-cell title="奖励次数">
          <template #right-icon>
            <van-stepper v-model="reward" min="0" max="50" integer style="margin-left: 10px" />
          </template>
        </van-cell>
        <p class="review-tip">填 0 表示仅通过、不发放奖励</p>
      </div>
    </van-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { showConfirmDialog, showSuccessToast, showFailToast } from 'vant'
import { getAllApplications, reviewApplication, updateApplicationStatus, reviewFeedback } from '../../api/admin'
import { STATUS, PURPOSE_TEXT } from '../../utils/constants'
import { readTypeNotifications } from '../../api/notification'
import { setUnread } from '../../store/notification'

const list = ref([])
const loading = ref(true)
const active = ref('pending')

const rejectShow = ref(false)
const rejectComment = ref('')
const rejectTarget = ref(null)

// 反馈通过：自选奖励次数
const reviewShow = ref(false)
const reviewTarget = ref(null)
const reward = ref(1)

function openReview(item) {
  reviewTarget.value = item
  reward.value = 1
  reviewShow.value = true
}

function beforeReviewClose(action) {
  if (action === 'confirm') {
    doReview(reviewTarget.value, 'approve', reward.value)
  }
  return true
}

// 分组定义：key / 标签 / 匹配函数（计数实时显示在 chip 上）
const CATS = [
  { key: 'pending', label: '待审批', match: (x) => x.status === 'pending' },
  { key: 'approved', label: '待打印', match: (x) => x.status === 'approved' },
  { key: 'completed', label: '打印完成', match: (x) => x.status === 'completed' },
  { key: 'unfed', label: '未反馈', match: (x) => x.status === 'completed' && !x.feedback_url },
  { key: 'fedback', label: '已反馈', match: (x) => !!x.feedback_url },
  { key: 'all', label: '全部申请', match: () => true },
]

const cats = computed(() =>
  CATS.map((c) => ({ ...c, count: list.value.filter(c.match).length || null })),
)
const activeLabel = computed(() => CATS.find((c) => c.key === active.value)?.label || '')
const shown = computed(() => {
  const c = CATS.find((x) => x.key === active.value)
  return c ? list.value.filter(c.match) : list.value
})

async function load() {
  loading.value = true
  try {
    list.value = await getAllApplications()
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

async function onReview(item, action) {
  if (action === 'approve') {
    openReview(item)
    return
  }
  const text = `拒绝「${item.apply_no}」的反馈？学生可重新上传。`
  try {
    await showConfirmDialog({ title: '反馈审核', message: text })
  } catch (e) {
    return
  }
  try {
    await reviewFeedback({ id: item.id, action })
    showSuccessToast('已拒绝')
    load()
  } catch (e) {
    /* 拦截器已提示 */
  }
}

async function doReview(item, action, rewardCount) {
  try {
    await reviewFeedback({ id: item.id, action, reward: rewardCount })
    showSuccessToast(action === 'approve' ? `已通过，奖励 ${rewardCount} 次已发放` : '已拒绝')
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
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 16px 4px;
}
.chip {
  border: 1px solid #e5e9f2;
  background: #fff;
  color: #4e5566;
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.chip.active {
  background: #2f6bff;
  border-color: #2f6bff;
  color: #fff;
}
.chip-count {
  font-size: 11px;
  background: rgba(0, 0, 0, 0.08);
  border-radius: 999px;
  padding: 0 6px;
}
.chip.active .chip-count {
  background: rgba(255, 255, 255, 0.25);
}
.admin-body {
  padding-top: 10px;
}
.admin-card {
  margin: 8px 16px;
  border-radius: 8px;
}
.reject-field {
  padding: 12px 16px;
}
.review-box {
  padding: 12px 16px 4px;
}
.review-item {
  font-size: 14px;
  font-weight: 600;
  color: #1a2233;
  margin-bottom: 8px;
}
.review-tip {
  margin: 8px 4px 0;
  font-size: 12px;
  color: #969799;
}
</style>
