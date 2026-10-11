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
      <div class="pd-task">正在打印：{{ snap.print_file || "N/A" }}</div>
      <div class="pd-remain" v-if="snap.remaining_time != null && snap.state === 'RUNNING'">
        剩余约 {{ fmtRemain(snap.remaining_time) }} · 预计 {{ etaText }} 完成
      </div>
      <div class="pd-remain" v-else-if="snap.online">{{ snap.state === 'FINISH' ? '本次打印已完成' : '待机中' }}</div>
      <div class="pd-updated">更新于 {{ snap.updated_at || '—' }} · 每 5 秒自动刷新</div>
    </div>

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
