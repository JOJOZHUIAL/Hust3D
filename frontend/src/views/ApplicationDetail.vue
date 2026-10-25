<template>
  <div class="page detail">
    <van-nav-bar title="申请详情" left-arrow fixed placeholder @click-left="$router.back()" />

    <van-skeleton v-if="loading" title :row="8" style="margin-top: 16px" />

    <template v-else-if="detail">
      <!-- 状态横幅 -->
      <div class="status-banner">
        <div class="status-tags">
          <van-tag :color="STATUS[detail.status]?.color" size="large" round>
            {{ STATUS[detail.status]?.text }}
          </van-tag>
          <van-tag v-if="detail.status === 'completed'" :color="detail.picked_up ? '#07c160' : '#ff976a'" size="large" round>
            {{ detail.picked_up ? '已领取' : '未领取' }}
          </van-tag>
          <van-tag v-if="detail.feedback_url && detail.feedback_reviewed === false" color="#ffd21e" size="large" round>反馈审核中</van-tag>
          <van-tag v-else-if="detail.feedback_url" color="#07c160" size="large" round>已反馈</van-tag>
          <van-tag v-else-if="detail.expired" color="#969799" size="large" round>已过期</van-tag>
          <van-tag v-else-if="detail.status === 'completed'" color="#ff976a" size="large" round>未反馈</van-tag>
        </div>
        <div class="apply-no">{{ detail.apply_no }}</div>
      </div>

      <!-- 申请人信息 -->
      <van-cell-group inset title="申请人信息">
        <van-cell title="姓名" :value="detail.applicant?.name || '—'" />
        <van-cell title="学号" :value="detail.applicant?.student_id || '—'" />
        <van-cell title="学院" :value="detail.applicant?.college || '—'" />
        <van-cell title="联系方式" :value="detail.applicant?.phone || '—'" />
      </van-cell-group>

      <!-- 打印需求 -->
      <van-cell-group inset title="打印需求">
        <van-cell
          title="用途"
          :value="(PURPOSE_TEXT[detail.purpose] || detail.purpose) + (detail.purpose_other ? '（' + detail.purpose_other + '）' : '')"
        />
        <van-cell title="期望材料" :value="detail.material" />
        <van-cell title="模型数量" :value="String(detail.model_count)" />
      </van-cell-group>

      <!-- 模型与说明 -->
      <van-cell-group inset title="模型与说明">
        <van-cell v-if="detail.file_url" title="模型文件" value="下载 STL" is-link @click="downloadFile" />
        <van-cell title="特别说明" :value="detail.remark || '无'" />
        <van-cell v-if="detail.sign_url" title="电子签名">
          <template #value>
            <img
              :src="assetUrl(detail.sign_url)"
              class="sign-img"
              alt="签名"
              @click="previewSign"
            />
          </template>
        </van-cell>
      </van-cell-group>

      <!-- 审批信息（审批人仅管理员可见） -->
      <van-cell-group v-if="detail.reviewed_at || detail.admin_comment || detail.reviewer" inset title="审批信息">
        <van-cell v-if="isAdmin" title="审批人" :value="personText(detail.reviewer)" />
        <van-cell title="审批时间" :value="detail.reviewed_at || '—'" />
        <van-cell v-if="detail.admin_comment" title="审批意见" :value="detail.admin_comment" />
      </van-cell-group>

      <!-- 打印信息（打印操作人仅管理员可见） -->
      <van-cell-group v-if="detail.printed_at || detail.completed_at || detail.printer" inset title="打印信息">
        <van-cell v-if="isAdmin" title="打印操作人" :value="personText(detail.printed_by)" />
        <van-cell title="开始打印" :value="detail.printed_at || '—'" />
        <van-cell v-if="detail.printer" title="打印机" :value="detail.printer.name || '—'" />
        <van-cell v-if="detail.printed_at || detail.completed_at" title="打印状态">
          <template #value>
            <!-- 只要已打印完成（不论人工标记还是打印机 100% 触发），一律显示完成 -->
            <span v-if="detail.status === 'completed' || detail.completed_at">打印完成</span>
            <span v-else-if="detail.print_matched">
              {{ stateText(detail.print_state) }}
              <template v-if="detail.print_progress != null"> · {{ detail.print_progress }}%</template>
            </span>
            <span v-else>等待打印机开始</span>
          </template>
        </van-cell>
        <van-cell
          v-if="detail.print_actual_file && !detail.print_matched && detail.status === 'printing'"
          title="打印机当前文件"
          :value="detail.print_actual_file"
        />
        <van-cell v-if="detail.completed_at" title="打印完成时间" :value="detail.completed_at" />
      </van-cell-group>

      <!-- 打印中：进度条 + 自动完成说明 -->
      <div v-if="detail.status === 'printing'" class="action-bar">
        <template v-if="detail.print_matched">
          <van-progress
            :percentage="detail.print_progress || 0"
            :show-pivot="true"
            stroke-width="8"
            color="#1989fa"
          />
          <p class="action-tip">
            打印机正在打印「{{ detail.file_name || '模型文件' }}」
            <template v-if="detail.printer"> · 打印机「{{ detail.printer.name }}」</template>
            <br />
            打印进度到 100% 时会自动标记完成（每 5 秒自动刷新）。
          </p>
        </template>
        <template v-else>
          <van-notice-bar
            left-icon="clock-o"
            wrapable
            :scrollable="false"
            :text="waitingText"
          />
          <p class="action-tip">
            已安排到打印机，但打印机当前还没开始打这一单；开始打印后会自动跟踪进度，
            到 100% 自动标记完成。
          </p>
        </template>
      </div>

      <!-- 取件短信（仅管理员，打印完成后自动发给申请人） -->
      <van-cell-group v-if="isAdmin && detail.status === 'completed'" inset title="取件短信">
        <van-cell title="接收手机号" :value="detail.applicant?.phone || '未填写'" />
        <van-cell title="发送状态">
          <template #value>
            <span v-if="detail.sms_sent_at" style="color: #07c160">已发送 {{ detail.sms_sent_at }}</span>
            <span v-else-if="detail.sms_result" style="color: #ee0a24">{{ detail.sms_result }}</span>
            <span v-else style="color: #969799">未发送</span>
          </template>
        </van-cell>
        <van-cell v-if="detail.sms_sent_at && detail.sms_result" title="网关返回" :value="detail.sms_result" />
        <van-cell>
          <div class="sms-btns">
            <van-button size="small" type="primary" round :loading="smsSending" @click="onSendSms">
              发送取件短信
            </van-button>
            <van-button size="small" plain round :loading="smsTesting" @click="onTestSms">
              测试网关
            </van-button>
          </div>
        </van-cell>
      </van-cell-group>

      <!-- 进度时间线 -->
      <div class="section-title">进度时间线</div>
      <div class="timeline-box">
        <van-steps direction="vertical" :active="activeStep" active-color="#07c160">
          <van-step v-for="s in detail.timeline" :key="s.title">
            <div class="step-title">{{ s.title }}</div>
            <div class="step-time">{{ s.time }}</div>
            <div v-if="s.operator && isAdmin" class="step-note">操作人：{{ s.operator }}</div>
            <div v-if="s.printer" class="step-note">打印机：{{ s.printer }}</div>
            <div v-if="s.note" class="step-note">{{ s.note }}</div>
          </van-step>
        </van-steps>
      </div>

      <!-- 撤回申请：仅待审批、仅本人（撤回=删除记录与文件，不消耗打印次数） -->
      <div v-if="detail.can_withdraw && isOwner" class="action-bar">
        <van-button plain round block type="danger" icon="revoke" :loading="withdrawing" @click="onWithdraw">
          撤回申请（不消耗打印次数）
        </van-button>
        <p class="action-tip">提交后发现填写有误可撤回；撤回后申请记录与模型文件将被删除。</p>
      </div>

      <!-- 导出申请表 Word -->
      <div class="action-bar">
        <van-button
          plain
          round
          block
          type="primary"
          icon="description-o"
          :loading="exporting"
          @click="onExport"
        >
          导出申请表（Word）
        </van-button>
      </div>

      <!-- 反馈超时过期提示（状态仍为已完成，只是不能再反馈领奖励） -->
      <div v-if="detail.expired" class="action-bar">
        <van-notice-bar
          left-icon="warning-o"
          wrapable
          :scrollable="false"
          :text="`该申请打印完成超过 ${detail.feedback_expire_days || 7} 天未提交反馈，已标记为已过期，反馈奖励不再发放。`"
        />
      </div>

      <!-- 已完成：反馈（上传实物图/现场照片，成功后奖励 1 次打印机会） -->
      <div v-if="detail.status === 'completed'" class="feedback-box">
        <template v-if="detail.feedback_url">
          <van-cell-group inset title="反馈">
            <van-cell title="反馈图片">
              <template #value>
                <img :src="assetUrl(detail.feedback_url)" class="feedback-img" alt="反馈图片" @click="previewFeedback" />
              </template>
            </van-cell>
            <van-cell title="反馈时间" :value="detail.feedback_at || '—'" />
          <van-cell v-if="detail.feedback_reviewed === false" title="审核状态" value="待管理员审核" />
          <van-cell v-else-if="detail.feedback_reviewed === 1" title="审核状态" value="已通过" />
          </van-cell-group>
        </template>
        <!-- 管理员：反馈审核 -->
        <div v-if="isAdmin && detail.feedback_reviewed === false" class="action-bar">
          <van-button type="success" round block @click="reviewShow = true">反馈通过（自选奖励）</van-button>
          <van-button type="danger" round block plain style="margin-top: 10px" @click="onFeedbackReview('reject')">反馈拒绝（可重传）</van-button>
        </div>
        <!-- 未过期才显示上传（过期后接口也会拦截） -->
        <div v-else-if="!detail.expired" class="action-bar">
          <van-uploader :after-read="onUploadFeedback" accept="image/*" :max-count="1">
            <van-button round block type="primary" :loading="submittingFeedback">
              上传实物图 / 现场照片
            </van-button>
          </van-uploader>
          <p class="feedback-tip">上传打印件用途的实物图或参赛现场照片，反馈成功后可领取 1 次打印机会。</p>
          <p v-if="detail.feedback_deadline" class="feedback-tip deadline">
            请在 {{ detail.feedback_deadline }} 前提交反馈，逾期将自动过期且不再发放奖励。
          </p>
        </div>
      </div>

      <!-- 管理员：状态推进 -->
      <div v-if="isAdmin && ['approved', 'printing'].includes(detail.status)" class="action-bar">
        <van-button
          v-if="detail.status === 'approved'"
          type="primary"
          round
          block
          icon="printer"
          @click="startPrint"
        >
          开始打印
        </van-button>
        <van-button
          v-if="detail.status === 'printing'"
          type="success"
          round
          block
          @click="advance('completed')"
        >
          标记完成
        </van-button>
        <van-button
          v-if="detail.status === 'printing'"
          plain
          round
          block
          icon="printer"
          style="margin-top: 10px"
          @click="startPrint"
        >
          更换打印机 / 重新指派
        </van-button>
      </div>
    </template>

    <!-- 开始打印：选择打印机（绑定后自动监视进度，100% 自动完成） -->
    <PrinterPicker ref="picker" @success="load" />

    <!-- 反馈通过：自选奖励次数 -->
    <van-dialog
      v-model:show="reviewShow"
      title="反馈通过"
      show-cancel-button
      :before-close="beforeReviewClose"
    >
      <div class="review-box">
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
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showConfirmDialog, showSuccessToast, showImagePreview } from 'vant'
import {
  getApplicationDetail,
  submitFeedback,
  exportApplicationForm,
  downloadAttachment,
  downloadBlob,
  withdrawApplication,
} from '../api/application'
import { updateApplicationStatus, reviewFeedback, resendSms, testSms } from '../api/admin'
import { useAuthStore } from '../store/auth'
import { assetUrl } from '../utils/server'
import PrinterPicker from '../components/PrinterPicker.vue'
import { STATUS, PURPOSE_TEXT } from '../utils/constants'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const detail = ref(null)
const loading = ref(true)
const submittingFeedback = ref(false)
const exporting = ref(false)
const withdrawing = ref(false)
const picker = ref(null)
let pollTimer = null

const isAdmin = computed(() => auth.isAdmin)
const isOwner = computed(() => !!detail.value && detail.value.user_id === auth.user?.id)
const activeStep = computed(() => (detail.value?.timeline?.length ? detail.value.timeline.length - 1 : 0))

// 打印机状态机 -> 中文（与后端 print_state 对应）
const STATE_TEXT = {
  RUNNING: '打印中',
  PAUSE: '已暂停',
  PAUSED: '已暂停',
  PREPARE: '准备中',
  SLICING: '切片中',
  FINISH: '打印完成',
  FAILED: '打印失败',
  IDLE: '空闲',
}

function stateText(state) {
  if (!state) return '—'
  return STATE_TEXT[String(state).toUpperCase()] || state
}

// 打印机当前在打别的文件时的提示文案
const waitingText = computed(() => {
  const actual = detail.value?.print_actual_file
  return actual
    ? `打印机当前正在打印其它文件：${actual}`
    : '打印机当前没有在打印本申请，等待开始…'
})

// 审批人/打印人展示为「姓名（学号）」
function personText(p) {
  if (!p) return '—'
  const name = (p.name || '').trim()
  const sid = (p.student_id || '').trim()
  if (name && sid) return `${name}（${sid}）`
  return name || sid || '—'
}

onMounted(() => {
  load()
  // 打印中时每 5 秒静默刷新一次进度（后台监视器回写 print_progress）
  pollTimer = setInterval(() => {
    if (detail.value?.status === 'printing') refreshSilently()
  }, 5000)
})

onUnmounted(() => clearInterval(pollTimer))

async function load() {
  loading.value = true
  try {
    detail.value = await getApplicationDetail(route.params.id)
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

// 打印中时静默刷新进度（不打断页面、不显示骨架屏）
async function refreshSilently() {
  if (document.hidden) return
  try {
    detail.value = await getApplicationDetail(route.params.id)
  } catch (e) {
    /* 拦截器已提示 */
  }
}

function startPrint() {
  picker.value?.open(detail.value)
}

async function downloadFile() {
  if (!detail.value?.file_url) return
  try {
    // 走命名下载接口：文件名为 姓名+申请编号（如 张三HUST3D20261011001.stl）
    const res = await downloadAttachment(detail.value.id, 'model')
    const ext = (detail.value.file_url || '').split('.').pop() || 'stl'
    downloadBlob(res.data, `${detail.value.applicant?.name || ''}${detail.value.apply_no}.${ext}`)
  } catch (e) {
    /* 拦截器已提示 */
  }
}

async function onExport() {
  exporting.value = true
  try {
    const res = await exportApplicationForm(detail.value.id)
    downloadBlob(res.data, `${detail.value.applicant?.name || ''}${detail.value.apply_no}.docx`)
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    exporting.value = false
  }
}

// 撤回申请：等价于删除（记录 + STL/签名文件），并返还 1 次打印机会
async function onWithdraw() {
  if (!detail.value) return
  try {
    await showConfirmDialog({
      title: '撤回申请',
      message: `确定撤回申请 ${detail.value.apply_no} 吗？\n撤回后记录与模型文件将被永久删除，且不消耗打印次数。`,
    })
  } catch (e) {
    return // 取消
  }
  withdrawing.value = true
  try {
    await withdrawApplication(detail.value.id)
    showSuccessToast('已撤回，打印次数已返还')
    router.replace('/applications')
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    withdrawing.value = false
  }
}

async function onUploadFeedback(file) {
  if (!file || !file.file) return
  submittingFeedback.value = true
  const fd = new FormData()
  fd.append('file', file.file)
  try {
    detail.value = await submitFeedback(detail.value.id, fd)
    showSuccessToast('反馈成功，已奖励 1 次打印机会')
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    submittingFeedback.value = false
  }
}

function previewFeedback() {
  if (detail.value?.feedback_url) {
    showImagePreview({
      images: [assetUrl(detail.value.feedback_url)],
      closeable: true,
      closeOnPopstate: true,
    })
  }
}

function previewSign() {
  if (detail.value?.sign_url) {
    showImagePreview({
      images: [assetUrl(detail.value.sign_url)],
      closeable: true,
      closeOnPopstate: true,
    })
  }
}

const reviewShow = ref(false)
const reward = ref(1)

function beforeReviewClose(action) {
  if (action === 'confirm') {
    onFeedbackReview('approve', reward.value)
  }
  return true
}

async function onFeedbackReview(action, rewardCount = 1) {
  if (action === 'reject') {
    const text = '拒绝该反馈？学生可重新上传。'
    try {
      await showConfirmDialog({ title: '反馈审核', message: text })
    } catch (e) {
      return
    }
  }
  try {
    detail.value = await reviewFeedback({ id: detail.value.id, action, reward: rewardCount })
    showSuccessToast(action === 'approve' ? `已通过，奖励 ${rewardCount} 次已发放` : '已拒绝')
  } catch (e) {
    /* 拦截器已提示 */
  }
}

// —— 取件短信（管理员）——
const smsSending = ref(false)
const smsTesting = ref(false)

async function onSendSms() {
  try {
    await showConfirmDialog({
      title: '发送取件短信',
      message: `确定给 ${detail.value.applicant?.phone || '申请人'} 发送取件短信吗？`,
    })
  } catch (e) {
    return
  }
  smsSending.value = true
  try {
    detail.value = await resendSms(detail.value.id)
    showSuccessToast('短信已发送')
  } catch (e) {
    /* 拦截器已提示失败原因 */
  } finally {
    smsSending.value = false
  }
}

async function onTestSms() {
  smsTesting.value = true
  try {
    await testSms(detail.value.applicant?.phone || '')
    showSuccessToast('测试短信已发送')
  } catch (e) {
    /* 拦截器已提示失败原因 */
  } finally {
    smsTesting.value = false
  }
}

// 手动标记完成（正常情况下打印到 100% 会自动完成，这里作为兜底）
async function advance(status) {  const text = status === 'printing' ? '确定开始打印该申请吗？' : '确定标记为已完成吗？'
  try {
    await showConfirmDialog({ title: '状态更新', message: text })
  } catch (e) {
    return // 取消
  }
  try {
    await updateApplicationStatus({ id: detail.value.id, status })
    showSuccessToast('状态已更新')
    load()
  } catch (e) {
    /* 拦截器已提示 */
  }
}
</script>

<style scoped>
.review-box {
  padding: 12px 16px 4px;
}
.review-tip {
  margin: 8px 4px 0;
  font-size: 12px;
  color: #969799;
}
.status-banner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 20px 16px;
  background: #fff;
  margin-bottom: 12px;
}
.status-tags {
  display: flex;
  gap: 8px;
}
.apply-no {
  font-size: 14px;
  color: #969799;
}
.feedback-img {
  height: 72px;
  border-radius: 6px;
  vertical-align: middle;
  cursor: pointer;
}
.feedback-tip {
  margin: 8px 4px 0;
  font-size: 12px;
  color: #969799;
}
.feedback-tip.deadline {
  color: #ff976a;
}
.action-tip {
  margin: 8px 4px 0;
  font-size: 12px;
  color: #969799;
  line-height: 1.5;
}
.timeline-box {
  margin: 0 16px;
  padding: 16px;
  background: #fff;
  border-radius: 8px;
}
.step-title {
  font-size: 14px;
  color: #323233;
}
.step-time {
  margin-top: 4px;
  font-size: 12px;
  color: #969799;
}
.step-note {
  margin-top: 2px;
  font-size: 12px;
  color: #2f6bff;
}
.sign-img {
  height: 48px;
  vertical-align: middle;
  cursor: pointer;
}
.action-bar {
  margin: 16px;
}
.sms-btns {
  display: flex;
  gap: 10px;
}
</style>
