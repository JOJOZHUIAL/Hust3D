<template>
  <div class="page admin page--wide">
    <van-nav-bar title="审批管理" left-arrow fixed placeholder @click-left="$router.replace('/admin')">
      <template #right>
        <span class="export-link" @click="openExport">导出</span>
      </template>
    </van-nav-bar>

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
          <van-tag v-if="item.status === 'completed' && !item.picked_up" color="#ff976a" style="margin-left: 6px">
            未领取
          </van-tag>
          <van-tag v-if="item.feedback_url && item.feedback_reviewed === false" color="#ffd21e" text-color="#ad6800" style="margin-left: 6px">
            反馈待审核
          </van-tag>
        </template>
        <template #desc>
          <div>{{ item.applicant?.name || '—' }} · {{ item.applicant?.college || '' }}</div>
          <div>{{ PURPOSE_TEXT[item.purpose] || item.purpose }} · {{ item.created_at }}</div>
          <div v-if="item.file_name" class="who-file">文件：{{ item.file_name }}</div>
          <div v-if="item.reviewer" class="who">审批人：{{ personText(item.reviewer) }}</div>
          <div v-if="item.printed_by" class="who">打印人：{{ personText(item.printed_by) }}</div>
          <div v-if="item.printer" class="who">
            打印机：{{ item.printer.name }}
            <template v-if="item.status === 'printing'">
              <span v-if="item.print_matched && item.print_progress != null"> · 打印中 {{ item.print_progress }}%</span>
              <span v-else class="warn">
                · 打印机当前在打别的文件{{ item.print_actual_file ? `（${item.print_actual_file}）` : '' }}，等待开始
              </span>
            </template>
            <span v-if="item.completed_auto"> · 自动完成</span>
          </div>
          <div v-else-if="item.status === 'printing'" class="who warn">
            未指派打印机（打印时若文件名含申请编号会自动认领）
          </div>
          <van-progress
            v-if="item.status === 'printing' && item.print_matched && item.print_progress != null"
            :percentage="item.print_progress"
            stroke-width="4"
            style="margin-top: 6px"
          />
        </template>
        <template #tags>
          <van-tag :color="STATUS[item.status]?.color">{{ STATUS[item.status]?.text }}</van-tag>
          <van-tag v-if="item.status === 'completed' && !item.picked_up" color="#ff976a">未领取</van-tag>
          <van-tag v-if="item.feedback_url && item.feedback_reviewed !== 2" color="#07c160">已反馈</van-tag>
          <van-tag v-else-if="item.expired" color="#969799">已过期</van-tag>
          <van-tag v-else-if="item.status === 'completed'" color="#ff976a">未反馈</van-tag>
        </template>
        <template #footer>
          <van-button v-if="item.status === 'pending'" size="small" type="primary" @click="onApprove(item)">通过</van-button>
          <van-button v-if="item.status === 'pending'" size="small" type="danger" @click="onReject(item)">拒绝</van-button>
          <van-button v-if="item.status === 'approved'" size="small" type="primary" @click="onStartPrint(item)">开始打印</van-button>
          <van-button v-if="item.status === 'printing'" size="small" type="success" @click="onAdvance(item, 'completed')">标记完成</van-button>
          <van-button
            v-if="item.status === 'approved' || item.status === 'printing'"
            size="small"
            plain
            type="danger"
            @click="openFailed(item)"
          >
            打印失败
          </van-button>
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

    <!-- 打印失败：原因必填，返还打印次数 -->
    <van-dialog
      v-model:show="failedShow"
      title="标记打印失败"
      show-cancel-button
      :before-close="beforeFailedClose"
    >
      <div class="reject-field">
        <van-field
          v-model="failedComment"
          type="textarea"
          rows="3"
          autosize
          placeholder="请填写打印失败原因（会通知学生并返还打印次数）"
        />
      </div>
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

    <!-- 开始打印：选择打印机（绑定后自动监视进度，100% 自动完成） -->
    <PrinterPicker ref="picker" @success="load" />

    <!-- 导出申请表：选时间范围，导出 ZIP（每个申请一个 Word） -->
    <van-popup v-model:show="exportShow" position="bottom" round :style="{ maxHeight: '88%' }">
      <div class="ex">
        <div class="ex-title">导出申请表</div>
        <div class="ex-sub">按申请提交时间筛选，导出为 ZIP 压缩包，里面每个申请一个独立的 Word 文件</div>

        <div class="ex-chips">
          <button
            v-for="c in EXPORT_CHIPS"
            :key="c.key"
            class="ex-chip"
            :class="{ active: exportMode === c.key }"
            type="button"
            @click="pickExportRange(c.key)"
          >
            {{ c.label }}
          </button>
        </div>

        <div class="ex-range">
          <div class="ex-range-row">
            <span class="ex-range-label">开始</span>
            <span class="ex-range-val">{{ exportStart || '不限' }}</span>
          </div>
          <div class="ex-range-row">
            <span class="ex-range-label">结束</span>
            <span class="ex-range-val">{{ exportEnd || '不限' }}</span>
          </div>
          <div class="ex-range-row">
            <span class="ex-range-label">数量</span>
            <span class="ex-range-val">{{ exportCount }} 份</span>
          </div>
        </div>

        <div class="ex-btns">
          <van-button round plain block @click="exportShow = false">取消</van-button>
          <van-button
            round
            type="primary"
            block
            :loading="exporting"
            :disabled="exportCount === 0"
            @click="onExport"
          >
            导出 Word
          </van-button>
        </div>
        <p class="ex-tip">单次最多导出 {{ MAX_EXPORT }} 份；导出内容为官方版式申请表。</p>
      </div>
    </van-popup>

    <!-- 自定义导出时间范围 -->
    <van-calendar
      v-model:show="calShow"
      type="range"
      allow-same-day
      title="选择导出时间范围"
      :min-date="calMinDate"
      :max-date="calMaxDate"
      @confirm="onCalConfirm"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { showConfirmDialog, showSuccessToast, showFailToast } from 'vant'
import {
  getAllApplications, reviewApplication, updateApplicationStatus, reviewFeedback, exportApplications,
} from '../../api/admin'
import { downloadBlob } from '../../api/application'
import { STATUS, PURPOSE_TEXT } from '../../utils/constants'
import { readTypeNotifications } from '../../api/notification'
import { setUnread } from '../../store/notification'
import PrinterPicker from '../../components/PrinterPicker.vue'

const route = useRoute()

const list = ref([])
const loading = ref(true)
// 支持 /admin/pending?cat=printing 直达某个分组
const active = ref('pending')
const picker = ref(null)

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
  { key: 'printing', label: '正在打印', match: (x) => x.status === 'printing' },
  { key: 'completed', label: '打印完成', match: (x) => x.status === 'completed' },
  { key: 'failed', label: '打印失败', match: (x) => x.status === 'failed' },
  { key: 'unfed', label: '未反馈', match: (x) => x.status === 'completed' && !x.feedback_url && !x.expired },
  { key: 'expired', label: '已过期', match: (x) => !!x.expired },
  { key: 'fedback', label: '已反馈', match: (x) => !!x.feedback_url },
  { key: 'all', label: '全部申请', match: () => true },
]

const cats = computed(() =>
  CATS.map((c) => ({ ...c, count: list.value.filter(c.match).length || null })),
)
const activeLabel = computed(() => CATS.find((c) => c.key === active.value)?.label || '')
const shown = computed(() => {
  const c = CATS.find((x) => x.key === active.value)
  const arr = c ? list.value.filter(c.match) : list.value
  // 已反馈分组：待审核的排最前面，其余按申请时间倒序
  if (active.value === 'fedback') {
    return [...arr].sort((a, b) => {
      const pa = a.feedback_reviewed === false ? 0 : 1
      const pb = b.feedback_reviewed === false ? 0 : 1
      if (pa !== pb) return pa - pb
      return new Date(b.created_at) - new Date(a.created_at)
    })
  }
  return arr
})

// 审批人/打印人展示为「姓名（学号）」
function personText(p) {
  if (!p) return '—'
  const name = (p.name || '').trim()
  const sid = (p.student_id || '').trim()
  if (name && sid) return `${name}（${sid}）`
  return name || sid || '—'
}

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

// 手动标记完成（正常情况下打印到 100% 会自动完成，这里作为兜底）
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

// —— 打印失败：原因弹窗（返还打印次数） ——
const failedShow = ref(false)
const failedTarget = ref(null)
const failedComment = ref('')

function openFailed(item) {
  failedTarget.value = item
  failedComment.value = ''
  failedShow.value = true
}

function beforeFailedClose(action) {
  if (action === 'confirm') {
    if (!failedComment.value.trim()) {
      showFailToast('请填写打印失败原因')
      return false
    }
    doFailed(failedTarget.value, failedComment.value.trim())
  }
  return true
}

async function doFailed(item, reason) {
  try {
    await updateApplicationStatus({ id: item.id, status: 'failed', reason })
    showSuccessToast('已标记打印失败，次数已返还')
    load()
  } catch (e) {
    /* 拦截器已提示 */
  }
}

// 开始打印：先选打印机，再绑定（绑定后后台自动监视进度，100% 时自动完成）
function onStartPrint(item) {
  picker.value?.open(item)
}

// —— 导出申请表：按提交时间范围导出 ZIP（里面每个申请一个 Word）——
const MAX_EXPORT = 300
const DAY = 86400000
const exportShow = ref(false)
const exporting = ref(false)
const exportMode = ref('month')
const exportStart = ref('')
const exportEnd = ref('')
const calShow = ref(false)
const calMinDate = new Date(2020, 0, 1)
const calMaxDate = new Date(Date.now() + 365 * DAY)

const EXPORT_CHIPS = [
  { key: 'month', label: '本月' },
  { key: 'lastMonth', label: '上月' },
  { key: '7d', label: '近七天' },
  { key: '30d', label: '近30天' },
  { key: 'all', label: '全部' },
  { key: 'custom', label: '自定义' },
]

function ymd(d) {
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

function rangeOf(key) {
  const now = new Date()
  const today = ymd(now)
  if (key === 'month') return [ymd(new Date(now.getFullYear(), now.getMonth(), 1)), today]
  if (key === 'lastMonth') {
    const first = new Date(now.getFullYear(), now.getMonth() - 1, 1)
    const last = new Date(now.getFullYear(), now.getMonth(), 0)
    return [ymd(first), ymd(last)]
  }
  if (key === '7d') return [ymd(new Date(now.getTime() - 6 * DAY)), today]
  if (key === '30d') return [ymd(new Date(now.getTime() - 29 * DAY)), today]
  return ['', ''] // 全部
}

function applyRange(key) {
  const [s, e] = rangeOf(key)
  exportStart.value = s
  exportEnd.value = e
}

function pickExportRange(key) {
  exportMode.value = key
  if (key === 'custom') {
    calShow.value = true
    return
  }
  applyRange(key)
}

function onCalConfirm(range) {
  const [a, b] = range
  exportMode.value = 'custom'
  exportStart.value = ymd(a)
  exportEnd.value = ymd(b)
  calShow.value = false
}

// 预估份数（本地按提交时间过滤，实际以后端为准）
const exportCount = computed(() => {
  const s = exportStart.value
  const e = exportEnd.value
  const startTs = s ? new Date(`${s.replace(/-/g, '/')} 00:00:00`).getTime() : -Infinity
  const endTs = e ? new Date(`${e.replace(/-/g, '/')} 23:59:59`).getTime() : Infinity
  const n = list.value.filter((x) => {
    const t = new Date((x.created_at || '').replace(/-/g, '/')).getTime()
    return t >= startTs && t <= endTs
  }).length
  return Math.min(n, MAX_EXPORT)
})

function openExport() {
  exportShow.value = true
  exportMode.value = 'month'
  applyRange('month')
}

async function onExport() {
  if (exportCount.value === 0) {
    showFailToast('该时间范围内没有申请')
    return
  }
  exporting.value = true
  try {
    const params = {}
    if (exportStart.value) params.start = exportStart.value
    if (exportEnd.value) params.end = exportEnd.value
    const res = await exportApplications(params)
    const blob = res.data
    // 后端返回业务错误时是 JSON，别把错误信息存成 .zip
    if (blob.type && blob.type.includes('json')) {
      let msg = '导出失败'
      try {
        msg = JSON.parse(await blob.text())?.msg || msg
      } catch (e) {
        /* 忽略解析失败 */
      }
      showFailToast(msg)
      return
    }
    const label = `${exportStart.value || '最早'}_${exportEnd.value || '最新'}`
    downloadBlob(new Blob([blob], { type: 'application/zip' }), `申请表_${label}_${exportCount.value}份.zip`)
    showSuccessToast('导出完成，解压后每份申请一个 Word')
    exportShow.value = false
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    exporting.value = false
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

let pollTimer = null

onMounted(() => {
  const want = route.query.cat
  if (want && CATS.some((c) => c.key === want)) active.value = want
  load()
  readTypeNotifications('apply').then(({ count }) => setUnread(count)).catch(() => {})
  // 看「正在打印」时自动刷新进度（后台监视器每 5 秒回写一次）
  pollTimer = setInterval(() => {
    if (!document.hidden && active.value === 'printing') load()
  }, 5000)
})

onUnmounted(() => clearInterval(pollTimer))
</script>

<style scoped>
.export-link {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  font-size: 13px;
  color: #2f6bff;
  cursor: pointer;
  border-radius: 999px;
  border: 1px solid rgba(47, 107, 255, 0.28);
}
.export-link:active {
  background: rgba(47, 107, 255, 0.08);
}
.ex {
  padding: 18px 16px 22px;
}
.ex-title {
  text-align: center;
  font-size: 16px;
  font-weight: 600;
  color: #1a2233;
}
.ex-sub {
  margin: 8px 4px 14px;
  font-size: 12px;
  line-height: 1.6;
  color: #969799;
  text-align: center;
}
.ex-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}
.ex-chip {
  border: 1px solid #e5e9f2;
  background: #fff;
  color: #4e5566;
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
}
.ex-chip.active {
  background: #2f6bff;
  border-color: #2f6bff;
  color: #fff;
}
.ex-range {
  margin: 16px 0 0;
  padding: 12px 14px;
  border-radius: 10px;
  background: #f7f9ff;
}
.ex-range-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  padding: 3px 0;
}
.ex-range-label {
  color: #969799;
}
.ex-range-val {
  color: #1a2233;
  font-weight: 600;
}
.ex-btns {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}
.ex-tip {
  margin: 12px 4px 0;
  font-size: 12px;
  line-height: 1.6;
  color: #969799;
  text-align: center;
}
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
.who {
  margin-top: 2px;
  font-size: 12px;
  color: #2f6bff;
}
.who .warn {
  color: #ff976a;
}
.who-file {
  margin-top: 2px;
  font-size: 12px;
  color: #646566;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
