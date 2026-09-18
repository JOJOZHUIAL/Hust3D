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
          <van-tag v-if="detail.feedback_url" color="#07c160" size="large" round>已反馈</van-tag>
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

      <!-- 审批意见 -->
      <van-cell-group v-if="detail.admin_comment" inset title="审批意见">
        <van-cell :value="detail.admin_comment" />
      </van-cell-group>

      <!-- 进度时间线 -->
      <div class="section-title">进度时间线</div>
      <div class="timeline-box">
        <van-steps direction="vertical" :active="activeStep" active-color="#07c160">
          <van-step v-for="s in detail.timeline" :key="s.title">
            <div class="step-title">{{ s.title }}</div>
            <div class="step-time">{{ s.time }}</div>
          </van-step>
        </van-steps>
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
          </van-cell-group>
        </template>
        <div v-else class="action-bar">
          <van-uploader :after-read="onUploadFeedback" accept="image/*" :max-count="1">
            <van-button round block type="primary" :loading="submittingFeedback">
              上传实物图 / 现场照片
            </van-button>
          </van-uploader>
          <p class="feedback-tip">上传打印件用途的实物图或参赛现场照片，反馈成功后可领取 1 次打印机会。</p>
        </div>
      </div>

      <!-- 管理员：状态推进 -->
      <div v-if="isAdmin && ['approved', 'printing'].includes(detail.status)" class="action-bar">
        <van-button
          v-if="detail.status === 'approved'"
          type="primary"
          round
          block
          @click="advance('printing')"
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
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { showConfirmDialog, showSuccessToast, showImagePreview } from 'vant'
import { getApplicationDetail, submitFeedback, exportApplicationForm, downloadBlob } from '../api/application'
import { updateApplicationStatus } from '../api/admin'
import { useAuthStore } from '../store/auth'
import { STATUS, PURPOSE_TEXT } from '../utils/constants'

const route = useRoute()
const auth = useAuthStore()
const isAdmin = computed(() => auth.isAdmin)

const detail = ref(null)
const loading = ref(true)
const submittingFeedback = ref(false)
const exporting = ref(false)

const activeStep = computed(() => (detail.value?.timeline?.length ? detail.value.timeline.length - 1 : 0))

onMounted(load)

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

function assetUrl(path) {
  // 后端返回的是相对路径（uploads/...），补上根路径
  return path.startsWith('http') ? path : '/' + path
}

function downloadFile() {
  if (detail.value?.file_url) window.open(assetUrl(detail.value.file_url))
}

async function onExport() {
  exporting.value = true
  try {
    const res = await exportApplicationForm(detail.value.id)
    downloadBlob(res.data, `3D打印服务申请表单-${detail.value.apply_no}.docx`)
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    exporting.value = false
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

async function advance(status) {
  const text = status === 'printing' ? '确定开始打印该申请吗？' : '确定标记为已完成吗？'
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
.sign-img {
  height: 48px;
  vertical-align: middle;
  cursor: pointer;
}
.action-bar {
  margin: 16px;
}
</style>
