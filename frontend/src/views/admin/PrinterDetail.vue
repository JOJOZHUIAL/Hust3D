<template>
  <div class="page pd">
    <van-nav-bar :title="snap.name || '打印机状态'" left-arrow fixed placeholder @click-left="$router.replace('/admin/printers')" />

    <!-- 状态大屏 -->
    <div class="pd-hero" :class="{ offline: !snap.online }">
      <div class="pd-state">
        {{ snap.online ? snap.state_text || '在线' : '离线' }}
      </div>
      <van-circle
        :current-rate="percentRate"
        :rate="percentRate"
        size="150px"
        layer-color="#ffffff26"
        :color="snap.state === 'RUNNING' ? '#ffd21e' : '#07c160'"
        :stroke-width="90"
        :text="percentText"
      />
      <div class="pd-task">正在打印：{{ taskFile }}</div>
      <div v-if="actuals.length" class="pd-job">
        对应 {{ actuals.length }} 份申请 · {{ actualApplicantText }} · 进度
        {{ progressOf(actuals[0]) }}%（到 100% 自动标记完成）
        <span v-if="actuals.some((a) => !a.tracked)"> · 有申请尚未在本系统点「开始打印」</span>
      </div>
      <div v-else-if="assignments.length" class="pd-job warn">
        打印机正在打的文件里没有本申请的编号 · 已指派
        {{ assignments.map((a) => a.apply_no).join("、") }} 等待开始
      </div>
      <div v-else-if="snap.online && job.task" class="pd-job">
        正在打印的文件里没有申请编号，无法自动关联申请（可手动标记完成）
      </div>
      <div v-else-if="snap.online" class="pd-job">打印机空闲</div>
      <div class="pd-remain" v-if="snap.remaining_time != null && snap.state === 'RUNNING'">
        剩余约 {{ fmtRemain(snap.remaining_time) }} · 预计 {{ etaText }} 完成
      </div>
      <div class="pd-remain" v-else-if="snap.online">{{ snap.state === 'FINISH' ? '本次打印已完成' : '待机中' }}</div>
      <div class="pd-updated">更新于 {{ snap.updated_at || '—' }} · 每 5 秒自动刷新</div>
    </div>

    <!-- 打印机真实任务（按文件名里的申请编号自动匹配，一盘多件会有多份） -->
    <van-cell-group v-if="actuals.length" inset title="打印机正在打印的申请" style="margin-top: 14px">
      <van-cell
        v-for="a in actuals"
        :key="a.id"
        :title="a.apply_no"
        :label="`${a.applicant || '—'} · ${a.file_name || '—'}`"
      >
        <template #value>
          <span>{{ progressOf(a) }}%</span>
        </template>
      </van-cell>
      <van-cell title="打印机文件名">
        <template #value>
          <span class="pd-file-name">{{ job.task || '—' }}</span>
        </template>
      </van-cell>
      <van-cell>
        <van-progress
          :percentage="progressOf(actuals[0])"
          :show-pivot="false"
          stroke-width="6"
          color="#1989fa"
        />
      </van-cell>
    </van-cell-group>

    <!-- 已指派到本机、但打印机还没开始打这些 -->
    <van-cell-group v-if="assignments.length" inset title="已指派、等待开始打印" style="margin-top: 14px">
      <van-cell
        v-for="a in assignments"
        :key="a.id"
        :title="a.apply_no"
        :label="`${a.applicant || '—'} · ${a.file_name || '—'}`"
      />
      <van-cell title="状态" value="打印机当前在打别的文件，等它开始打这单后会自动跟踪进度" />
    </van-cell-group>

    <p class="pd-tip">
      自动完成按打印机上报的文件名里的申请编号匹配（拓竹的打印文件名形如
      「丘馗HUST3D20261017005.stl」）。打印机在打别的文件、或文件名里没有申请编号时，
      不会把本申请判为完成，可用「标记完成」人工处理。
    </p>

    <!-- 温度面板 -->
    <div class="pd-grid">
      <div class="pd-box">
        <div class="pd-num">{{ snap.nozzle_temp != null ? snap.nozzle_temp : '—' }}<span>℃</span></div>
        <div class="pd-label">喷头温度</div>
      </div>
      <div class="pd-box">
        <div class="pd-num">{{ snap.bed_temp != null ? snap.bed_temp : '—' }}<span>℃</span></div>
        <div class="pd-label">热床温度</div>
      </div>
      <div class="pd-box">
        <div class="pd-num">{{ snap.chamber_temp != null ? snap.chamber_temp : '—' }}<span>℃</span></div>
        <div class="pd-label">腔体温度</div>
      </div>
    </div>

    <!-- 设备信息 -->
    <van-cell-group inset style="margin-top: 14px">
      <van-cell title="打印机" :value="snap.name" />
      <van-cell title="IP 地址" :value="snap.ip" />
      <van-cell title="序列号" :value="snap.serial || '自动发现中…'" />
      <van-cell title="连接状态" :value="snap.online ? '在线（MQTT）' : '离线'" />
    </van-cell-group>

    <p class="pd-tip">状态由服务器通过拓竹局域网 MQTT 直连打印机获取，无需拓竹账号。</p>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { getPrinterStatus } from '../../api/printer'

const route = useRoute()
const printerId = route.params.id
const snap = ref({ name: '', ip: '', serial: null, online: false, state_text: '连接中' })
let timer = null

// 打印机当前任务（后端按文件名里的申请编号匹配，一盘多件会有多份）
const job = computed(() => snap.value.job || {})
const actuals = computed(() => job.value.actuals || [])
const assignments = computed(() => job.value.assignments || [])
// 打印机上报的真实文件名：优先 task_name（如 丘馗HUST3D20261017005 + … .stl）
const taskFile = computed(
  () => job.value.task || snap.value.task_name || snap.value.print_file || 'N/A',
)
// 一盘多件时列出涉及的学生
const actualApplicantText = computed(() => {
  const names = actuals.value.map((a) => a.applicant).filter(Boolean)
  return names.length ? names.join("、") : "—"
})

function progressOf(a) {
  return a && a.progress != null ? a.progress : 0
}

const percentRate = computed(() => Number(snap.value.percent) || 0)

// 预计完成时间 = 当前时间 + 剩余分钟（随每次轮询实时校正）
const etaText = computed(() => {
  const raw = snap.value.remaining_time
  if (raw == null || raw === '') return ''
  const min = Number(raw)
  if (!Number.isFinite(min)) return ''
  const eta = new Date(Date.now() + min * 60 * 1000)
  const pad = (n) => String(n).padStart(2, '0')
  const hm = `${pad(eta.getHours())}:${pad(eta.getMinutes())}`
  const today = new Date()
  if (eta.toDateString() === today.toDateString()) return `今天 ${hm}`
  const tomorrow = new Date(today.getTime() + 86400000)
  if (eta.toDateString() === tomorrow.toDateString()) return `明天 ${hm}`
  return `${pad(eta.getMonth() + 1)}-${pad(eta.getDate())} ${hm}`
})
const percentText = computed(() => {
  if (!snap.value.online) return '离线'
  if (snap.value.percent == null) return snap.value.state_text || '—'
  return `${snap.value.percent}%`
})

function fmtRemain(sec) {
  const m = Math.round(Number(sec) || 0)
  if (m < 60) return `${m} 分钟`
  const hh = Math.floor(m / 60)
  return `${hh} 小时 ${m % 60} 分`
}

async function load() {
  if (document.hidden) return
  try {
    snap.value = await getPrinterStatus(printerId)
  } catch (e) {
    /* 拦截器已提示 */
  }
}

onMounted(() => {
  load()
  timer = setInterval(load, 5000)
})

onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.pd {
  padding-bottom: 40px;
}
.pd-hero {
  margin: 12px 16px 0;
  padding: 28px 20px;
  border-radius: 18px;
  background: linear-gradient(135deg, #1f3a6e, #2f6bff);
  color: #fff;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.pd-hero.offline {
  background: linear-gradient(135deg, #6b7280, #9ca3af);
}
.pd-state {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 2px;
}
.pd-remain {
  font-size: 14px;
  opacity: 0.92;
}
.pd-job {
  font-size: 12px;
  line-height: 1.6;
  opacity: 0.9;
  text-align: center;
  padding: 0 8px;
}
.pd-job.warn {
  color: #ffd21e;
}
.pd-file-name {
  font-size: 12px;
  word-break: break-all;
  text-align: right;
}
.pd-updated {
  font-size: 11px;
  opacity: 0.6;
}

.pd-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin: 14px 16px 0;
}
.pd-box {
  background: #fff;
  border-radius: 12px;
  padding: 14px 6px;
  text-align: center;
  box-shadow: 0 4px 14px rgba(20, 46, 104, 0.06);
}
.pd-num {
  font-size: 20px;
  font-weight: 700;
  color: #2f6bff;
}
.pd-num span {
  font-size: 12px;
  font-weight: 400;
  color: #969799;
  margin-left: 2px;
}
.pd-label {
  margin-top: 4px;
  font-size: 12px;
  color: #969799;
}
.pd-tip {
  margin: 14px 20px 0;
  font-size: 12px;
  line-height: 1.7;
  color: #969799;
}
</style>
