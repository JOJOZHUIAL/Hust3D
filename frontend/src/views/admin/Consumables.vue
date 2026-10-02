<template>
  <div class="page consumables">
    <van-nav-bar title="耗材管理" left-arrow fixed placeholder @click-left="$router.replace('/admin')" />

    <!-- 扫码区：入库/拆封共用 -->
    <div class="scan-section">
      <div class="reader-wrap">
        <!-- 自管摄像头流 + ZBar(WASM) 逐帧识别：
             html5-qrcode 的 JS 版 ZXing 在部分国产机 WebView 上解不出细条纹一维码，
             ZBar 引擎实测可解出本项目耗材条码（CODE128） -->
        <div class="reader">
          <video v-show="scanning" ref="scanVideo" class="scan-video" playsinline muted autoplay></video>
        </div>
        <div v-if="!scanning" class="reader-off" @click="startScan">
          <van-icon name="scan" size="34" />
          <div class="reader-tip">点击开始扫码</div>
          <div class="reader-sub">对准耗材条形码，自动识别数字</div>
        </div>
      </div>
      <div v-if="scanning" class="reader-actions">
        <span class="scan-live-tip">对准条形码保持稳定，1-2 秒内自动识别</span>
        <van-button size="small" plain round @click="stopScan">关闭摄像头</van-button>
      </div>

      <!-- 手动输入兜底（电脑端 / 摄像头不可用时） -->
      <div class="manual-row">
        <van-field
          v-model="barcode"
          class="manual-input"
          placeholder="或手动输入条形码数字"
          type="digit"
          clearable
          @keyup.enter="doLookup"
        />
        <van-button type="primary" size="small" round :loading="looking" @click="doLookup">
          查询
        </van-button>
      </div>
      <div v-if="lastResultMsg" class="scan-msg" :class="{ ok: lastOk }">{{ lastResultMsg }}</div>

      <!-- 非安全上下文（局域网 http 访问）时提示手机走 HTTPS 开摄像头 -->
      <div v-if="phoneHelp.show" class="phone-help">
        <div class="ph-title">📷 手机开启摄像头扫码</div>
        <div class="ph-text">
          手机浏览器扫码打开下方地址（首次需点「高级 → 继续前往」，自签名证书仅内网使用），
          登录后即可在本页用摄像头扫码：
        </div>
        <canvas ref="qrCanvas" class="ph-qr"></canvas>
        <div class="ph-url">https://{{ phoneHelp.ip }}:{{ phoneHelp.port }}/#/admin/consumables</div>
        <div class="ph-note" @click="phoneHelp.open = !phoneHelp.open">
          {{ phoneHelp.open ? '收起说明 ▲' : '打不开？看说明 ▼' }}
        </div>
        <div v-if="phoneHelp.open" class="ph-detail">
          <p>1. 电脑先运行 backend\scripts\generate_cert.bat 生成证书并重启后端；</p>
          <p>2. 手机与电脑连同一个 Wi-Fi，扫码或输入上面地址；</p>
          <p>3. 浏览器提示「您的连接不是私密连接」时，点「高级」→「继续前往」；</p>
          <p>4. 若仍无法调起摄像头（部分 iOS 版本限制），可在电脑上用摄像头，或本页手动输入条形码。</p>
        </div>
      </div>
    </div>

    <van-tabs v-model:active="tab" sticky>
      <!-- 拆封（高频操作，置于首位） -->
      <van-tab title="拆封" name="open">
        <div class="form-pad">
          <template v-if="lookup?.exists">
            <div class="item-card">
              <div class="item-name">{{ lookup.item.name }}</div>
              <div class="item-meta">
                {{ lookup.item.material || '—' }} · {{ lookup.item.color || '—' }} · 条码 {{ lookup.item.barcode }}
              </div>
              <div class="item-stock">{{ lookup.item.quantity }}<span> {{ lookup.item.unit }}</span></div>
            </div>
            <van-field
              v-model="openNote"
              label="备注"
              placeholder="用途 / 对应申请单号（选填）"
              maxlength="255"
              style="margin-top: 12px"
            />
            <div class="submit-row">
              <van-button type="danger" round block :loading="submitting" @click="onOpen">
                确认拆封（库存 -1）
              </van-button>
            </div>
          </template>
          <van-empty v-else :description="lookup ? '该条形码尚未入库，请先到「入库」登记' : '扫码或输入条形码后显示耗材信息'" />
        </div>
      </van-tab>

      <!-- 入库 -->
      <van-tab title="入库" name="in">
        <div class="form-pad">
          <div v-if="lookup?.exists" class="exist-tip">
            已有台账：{{ lookup.item.name }} · 当前库存 {{ lookup.item.quantity }} {{ lookup.item.unit }}，本次入库将累加
          </div>
          <div v-else-if="lookup" class="exist-tip new">新条形码，请登记耗材信息建档</div>

          <van-cell-group inset>
            <van-field v-model="form.barcode" label="条形码" placeholder="扫码后自动填入" readonly />
            <van-field v-model="form.name" label="名称" placeholder="如：PLA 1.75mm 打印耗材" maxlength="128" required />
            <van-field v-model="form.material" label="材质" placeholder="如 PLA / PETG / 树脂" maxlength="64" />
            <van-field v-model="form.color" label="颜色" placeholder="如 黑色 / 白色" maxlength="64" />
            <van-field v-model="form.quantity" label="数量" type="digit" placeholder="本次入库数量" maxlength="4" required />
            <van-field v-model="form.unit" label="单位" placeholder="卷 / 盒 / 桶" maxlength="16" />
            <van-field v-model="form.note" label="备注" placeholder="进货单号等（选填）" maxlength="255" />
          </van-cell-group>

          <div class="submit-row">
            <van-button type="primary" round block :loading="submitting" @click="onStockIn">
              登记入库
            </van-button>
          </div>
          <p class="hint">登记人员与入库时间由系统按登录账号和提交时刻自动记录。</p>
        </div>
      </van-tab>

      <!-- 台账 -->
      <van-tab title="台账" name="stock">
        <div class="form-pad">
          <van-search v-model="stockKeyword" placeholder="按名称 / 材质 / 颜色 / 条码筛选" shape="round" />
          <van-cell-group inset>
            <van-cell v-for="it in filteredItems" :key="it.id" :title="it.name" :label="`${it.material || '—'} · ${it.color || '—'} · ${it.barcode}`">
              <template #value>
                <span class="stock-num" :class="{ low: it.quantity <= 1 }">{{ it.quantity }}</span> {{ it.unit }}
              </template>
            </van-cell>
          </van-cell-group>
          <van-empty v-if="!filteredItems.length" :description="stockKeyword ? '没有匹配的耗材' : '暂无耗材，先去「入库」登记'" />
        </div>
      </van-tab>

      <!-- 流水 -->
      <van-tab title="流水记录" name="logs">
        <div class="form-pad">
          <van-cell-group inset>
            <van-cell v-for="log in logs" :key="log.id">
              <template #title>
                <span class="log-tag" :class="log.action">
                  {{ log.action === 'in' ? `入库 +${log.quantity_change}` : `拆封 ${log.quantity_change}` }}
                </span>
                <span class="log-name">{{ log.name || log.barcode }}</span>
              </template>
              <template #label>
                {{ log.material || '—' }}/{{ log.color || '—' }} · 操作人 {{ log.operator || '—' }} · 余 {{ log.quantity_after }} {{ log.unit || '' }}
                <template v-if="log.note"> · {{ log.note }}</template>
                <br />{{ (log.created_at || '').slice(0, 16) }}
              </template>
            </van-cell>
          </van-cell-group>
          <van-empty v-if="!logs.length" description="暂无进出记录" />
        </div>
      </van-tab>
    </van-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { showConfirmDialog, showSuccessToast, showFailToast } from 'vant'
import QRCode from 'qrcode'
import { scanImageData } from '@undecaf/zbar-wasm'
import { useAuthStore } from '../../store/auth'
import { getLanInfo } from '../../api/system'
import {
  scanConsumable, stockInConsumable, openConsumable,
  getConsumableLogs, getConsumableList,
} from '../../api/consumable'

const auth = useAuthStore()

const tab = ref('open') // 拆封是高频操作，默认置于首位
const barcode = ref('')
const scanning = ref(false)
const looking = ref(false)
const submitting = ref(false)
const lookup = ref(null) // { exists, item }
const lastResultMsg = ref('')
const lastOk = ref(false)

const form = ref({ barcode: '', name: '', material: '', color: '', quantity: '', unit: '卷', note: '' })
const openNote = ref('')
const items = ref([])
const scanVideo = ref(null)
const logs = ref([])

// 手机扫码帮助：局域网 http 访问（非安全上下文）时展示 HTTPS 二维码
const qrCanvas = ref(null)
const phoneHelp = ref({ show: false, ip: '', port: 5443, open: false })

async function initPhoneHelp() {
  if (window.isSecureContext) return // 已是 https/localhost，摄像头天然可用
  try {
    const lan = await getLanInfo()
    if (!lan.https_enabled || !lan.ips?.length) return
    phoneHelp.value = {
      show: true,
      ip: lan.ips[0],
      port: lan.https_port,
      open: false,
    }
    const url = `https://${lan.ips[0]}:${lan.https_port}/#/admin/consumables`
    await nextTick()
    if (qrCanvas.value) {
      await QRCode.toCanvas(qrCanvas.value, url, { width: 168, margin: 1 })
    }
  } catch (e) {
    /* 忽略，面板不显示 */
  }
}

let mediaStream = null
let scanTimer = null
let beepCtx = null

// —— 扫码：自管摄像头流 + ZBar(WASM) 逐帧识别 ——
async function startScan() {
  if (scanning.value) return
  try {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('当前环境不支持摄像头')
    }
    await nextTick()
    // 一维码条纹细，请求高分辨率视频流
    mediaStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } },
      audio: false,
    })
    const video = scanVideo.value
    video.srcObject = mediaStream
    await video.play().catch(() => {})
    scanning.value = true
    startScanLoop()
  } catch (e) {
    await stopScan()
    console.error('[scan] 启动失败:', e)
    showFailToast('摄像头启动失败：' + String(e?.message || e).slice(0, 60))
  }
}

function startScanLoop() {
  const video = scanVideo.value
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d', { willReadFrequently: true })
  let busy = false
  scanTimer = setInterval(async () => {
    if (busy || !video.videoWidth) return
    busy = true
    try {
      // 限制最大宽度控制每帧开销，同时保留一维码细节
      const scale = Math.min(1, 1280 / video.videoWidth)
      canvas.width = Math.round(video.videoWidth * scale)
      canvas.height = Math.round(video.videoHeight * scale)
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)
      const symbols = await scanImageData(imageData)
      const hit = symbols.find((s) => s.decode && s.decode())
      if (hit) {
        beep()
        await stopScan()
        barcode.value = hit.decode().trim()
        await doLookup()
        return
      }
    } catch (e) {
      /* 单帧解码失败忽略，下一帧重试 */
    } finally {
      busy = false
    }
  }, 150)
}

async function stopScan() {
  if (scanTimer) {
    clearInterval(scanTimer)
    scanTimer = null
  }
  mediaStream?.getTracks().forEach((t) => t.stop())
  mediaStream = null
  const video = scanVideo.value
  if (video) video.srcObject = null
  scanning.value = false
}

function beep() {
  try {
    beepCtx = beepCtx || new (window.AudioContext || window.webkitAudioContext)()
    const osc = beepCtx.createOscillator()
    const gain = beepCtx.createGain()
    osc.frequency.value = 1200
    gain.gain.setValueAtTime(0.12, beepCtx.currentTime)
    gain.gain.exponentialRampToValueAtTime(0.001, beepCtx.currentTime + 0.15)
    osc.connect(gain).connect(beepCtx.destination)
    osc.start()
    osc.stop(beepCtx.currentTime + 0.15)
  } catch (e) {
    /* 无声环境忽略 */
  }
}

// —— 查询 ——
async function doLookup() {
  const bc = barcode.value.trim()
  if (!bc) {
    showFailToast('请扫码或输入条形码')
    return
  }
  looking.value = true
  try {
    lookup.value = await scanConsumable(bc)
    form.value.barcode = bc
    lastOk.value = lookup.value.exists
    if (lookup.value.exists) {
      const it = lookup.value.item
      // 已有台账：预填名称/材质/颜色，数量留空
      form.value.name = it.name
      form.value.material = it.material || ''
      form.value.color = it.color || ''
      form.value.unit = it.unit || '卷'
      form.value.quantity = ''
      lastResultMsg.value = `已找到：${it.name}（库存 ${it.quantity} ${it.unit}）`
    } else {
      lastResultMsg.value = '新条形码，请在「入库」中登记建档'
    }
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    looking.value = false
  }
}

// —— 入库 ——
async function onStockIn() {
  if (!form.value.barcode) {
    showFailToast('请先扫码或输入条形码')
    return
  }
  if (!form.value.name.trim()) {
    showFailToast('请填写耗材名称')
    return
  }
  const qty = parseInt(form.value.quantity, 10)
  if (!qty || qty < 1) {
    showFailToast('请填写正确的入库数量')
    return
  }
  submitting.value = true
  try {
    const item = await stockInConsumable({
      barcode: form.value.barcode,
      name: form.value.name.trim(),
      material: form.value.material.trim(),
      color: form.value.color.trim(),
      unit: form.value.unit.trim() || '卷',
      quantity: qty,
      note: form.value.note.trim(),
    })
    lookup.value = { exists: true, item }
    lastResultMsg.value = `入库成功：${item.name} 现有 ${item.quantity} ${item.unit}`
    lastOk.value = true
    form.value.quantity = ''
    form.value.note = ''
    showSuccessToast('入库成功')
    loadStock()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    submitting.value = false
  }
}

// —— 拆封 ——
async function onOpen() {
  if (!lookup.value?.exists) return
  try {
    await showConfirmDialog({
      title: '拆封确认',
      message: `确认拆封「${lookup.value.item.name}」吗？\n将以 ${auth.user?.name || '当前管理员'} 的名义记录拆封，库存 -1。`,
    })
  } catch (e) {
    return // 取消
  }
  submitting.value = true
  try {
    const item = await openConsumable({ barcode: form.value.barcode, note: openNote.value.trim() })
    lookup.value = { exists: true, item }
    lastResultMsg.value = `拆封成功：${item.name} 剩余 ${item.quantity} ${item.unit}`
    openNote.value = ''
    showSuccessToast('拆封成功')
    loadStock()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    submitting.value = false
  }
}

async function loadStock() {
  try {
    items.value = await getConsumableList()
  } catch (e) {
    /* 忽略 */
  }
}

async function loadLogs() {
  try {
    logs.value = await getConsumableLogs(100)
  } catch (e) {
    /* 忽略 */
  }
}

watch(tab, (t) => {
  if (t === 'logs') loadLogs()
  if (t === 'stock') loadStock()
})

onMounted(() => {
  loadStock()
  initPhoneHelp()
})

onUnmounted(() => {
  stopScan()
  beepCtx?.close?.()
})
</script>

<style scoped>
.consumables {
  padding-bottom: 40px;
}
.scan-section {
  padding: 14px 16px 6px;
}
.reader-wrap {
  position: relative;
  width: 100%;
}
.reader {
  width: 100%;
  height: 230px;
  border-radius: 12px;
  overflow: hidden;
  background: #101828;
  display: grid;
  place-items: center;
}
.scan-video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 12px;
  background: #000;
}
.reader-off {
  position: absolute;
  inset: 0;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #2f6bff;
  cursor: pointer;
  background: #fff;
}
.reader-tip {
  font-size: 15px;
  font-weight: 600;
}
.reader-sub {
  font-size: 12px;
  color: #969799;
}
.reader-actions {
  width: 100%;
  min-height: 48px;
  margin-top: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.scan-live-tip {
  font-size: 12px;
  color: #969799;
}
.manual-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}
.manual-input {
  flex: 1;
  background: #f7f8fa;
  border-radius: 8px;
}
.scan-msg {
  margin-top: 8px;
  font-size: 13px;
  color: #ee0a24;
}
.scan-msg.ok {
  color: #07c160;
}

/* 手机扫码帮助面板 */
.phone-help {
  margin-top: 14px;
  padding: 14px;
  border-radius: 12px;
  background: #f0f5ff;
  text-align: center;
}
.ph-title {
  font-size: 14px;
  font-weight: 600;
  color: #1a2233;
}
.ph-text {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: #646566;
  text-align: left;
}
.ph-qr {
  margin-top: 10px;
  background: #fff;
  border-radius: 8px;
  padding: 6px;
}
.ph-url {
  margin-top: 8px;
  font-size: 12px;
  font-weight: 600;
  color: #2f6bff;
  word-break: break-all;
}
.ph-note {
  margin-top: 8px;
  font-size: 12px;
  color: #969799;
  cursor: pointer;
}
.ph-detail {
  margin-top: 8px;
  text-align: left;
}
.ph-detail p {
  margin: 4px 0;
  font-size: 12px;
  line-height: 1.6;
  color: #969799;
}

.form-pad {
  padding-top: 12px;
  padding-bottom: 24px;
}
.exist-tip {
  margin: 0 16px 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: #e8f5ee;
  color: #07c160;
  font-size: 13px;
}
.exist-tip.new {
  background: #fff7ef;
  color: #ff976a;
}
.submit-row {
  margin: 16px 16px 0;
}
.hint {
  margin: 12px 20px 0;
  font-size: 12px;
  color: #969799;
}

.item-card {
  margin: 0 16px;
  padding: 18px 20px;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 4px 16px rgba(20, 46, 104, 0.06);
}
.item-name {
  font-size: 17px;
  font-weight: 600;
  color: #1a2233;
}
.item-meta {
  margin-top: 6px;
  font-size: 12px;
  color: #969799;
}
.item-stock {
  margin-top: 10px;
  font-size: 34px;
  font-weight: 700;
  color: #2f6bff;
  line-height: 1;
}
.item-stock span {
  font-size: 13px;
  font-weight: 400;
  color: #969799;
}

.stock-num {
  font-size: 18px;
  font-weight: 700;
  color: #2f6bff;
}
.stock-num.low {
  color: #ee0a24;
}
.log-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  margin-right: 8px;
}
.log-tag.in {
  background: #e8f5ee;
  color: #07c160;
}
.log-tag.open {
  background: #fde8e8;
  color: #ee0a24;
}
.log-name {
  font-size: 14px;
  color: #323233;
}
</style>
