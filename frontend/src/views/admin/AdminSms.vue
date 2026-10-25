<template>
  <div class="sms-page">
    <!-- 页头：右上角 + 添加监听窗口 -->
    <div class="page-head">
      <span class="page-title">短信通知</span>
      <van-icon name="plus" class="head-add" @click="openAdd" />
    </div>

    <!-- 网关状态 -->
    <div class="gate-card" :class="status.reachable ? 'ok' : 'warn'">
      <div class="gate-row">
        <span class="gate-dot" />
        <span class="gate-title">
          {{ !status.enabled ? '短信通知未启用' : status.reachable ? '网关在线' : '网关离线' }}
        </span>
        <span v-if="status.pending" class="pending-badge">待发送 {{ status.pending }}</span>
      </div>
      <div v-if="gateways.length" class="gate-list">
        <div v-for="gw in gateways" :key="gw.url" class="gate-item">
          <span class="gw-dot" :class="{ on: gw.reachable }" />
          <span class="gw-url">{{ gw.url }}</span>
          <van-icon name="cross" class="gw-del" @click="onRemove(gw)" />
        </div>
      </div>
      <div v-else class="gate-tip">还没有监听窗口，点右上角 + 添加</div>
      <div class="gate-tip">{{ gateTip }}</div>
    </div>

    <!-- 自定义发送 -->
    <van-cell-group inset title="发送短信">
      <van-field
        v-model="form.phone"
        label="手机号"
        placeholder="11 位手机号"
        maxlength="11"
        type="tel"
        clearable
      />
      <van-field
        v-model="form.content"
        label="内容"
        type="textarea"
        rows="3"
        maxlength="500"
        show-word-limit
        placeholder="请输入短信内容"
        autosize
      />
      <van-cell>
        <van-button
          type="primary"
          block
          round
          :loading="sending"
          :disabled="!form.phone || !form.content"
          @click="onSend"
        >
          发送
        </van-button>
      </van-cell>
    </van-cell-group>

    <!-- 记录 -->
    <van-cell-group inset title="发送记录">
      <template #title>
        <div class="list-head">
          <span>发送记录</span>
          <van-tabs v-model:active="activeStatus" shrink @change="loadList(1)">
            <van-tab title="全部" name="" />
            <van-tab :title="`待发送${counts.pending ? ' ' + counts.pending : ''}`" name="pending" />
            <van-tab :title="`已发送${counts.sent ? ' ' + counts.sent : ''}`" name="sent" />
            <van-tab :title="`失败${counts.failed ? ' ' + counts.failed : ''}`" name="failed" />
          </van-tabs>
        </div>
      </template>

      <van-empty v-if="!loading && items.length === 0" description="暂无短信记录" />
      <div v-for="it in items" :key="it.id" class="msg-item">
        <div class="msg-top">
          <span class="msg-phone">{{ it.phone }}</span>
          <van-tag :type="statusType(it.status)" round>{{ statusText(it.status) }}</van-tag>
        </div>
        <div class="msg-content">{{ it.content }}</div>
        <div class="msg-meta">
          <span>{{ it.created_at }}</span>
          <span v-if="it.kind === 'pickup'" class="kind">取件通知 · {{ it.apply_no }}</span>
          <span v-else-if="it.kind === 'test'" class="kind">测试</span>
          <span v-else-if="it.sender_name" class="kind">由 {{ it.sender_name }} 发送</span>
        </div>
        <div v-if="it.status !== 'sent'" class="msg-actions">
          <span v-if="it.last_error" class="msg-error">{{ it.last_error }}</span>
          <div class="msg-btns">
            <van-button size="mini" plain type="primary" round @click="onRetry(it)">重发</van-button>
            <van-button size="mini" plain type="danger" round @click="onDelete(it)">删除</van-button>
          </div>
        </div>
        <div v-else class="msg-actions">
          <span class="msg-ok">已发送 {{ it.sent_at }}</span>
        </div>
      </div>

      <van-cell v-if="items.length < total" style="text-align: center">
        <van-button size="small" plain round :loading="loading" @click="loadList(page + 1)">
          加载更多
        </van-button>
      </van-cell>
    </van-cell-group>

    <!-- 添加监听窗口 -->
    <van-popup v-model:show="addShow" position="bottom" round :style="{ paddingBottom: '12px' }">
      <div class="add-box">
        <div class="add-title">添加监听窗口</div>
        <van-field
          v-model="newUrl"
          label="地址"
          placeholder="http://192.168.1.130:5000/sms/send"
          clearable
        />
        <div class="add-tip">
          多台手机的短信网关会按顺序尝试，谁在线就用谁；全部离线时短信先存起来，手机回网后自动补发。
        </div>
        <div class="add-btns">
          <van-button block round @click="addShow = false">取消</van-button>
          <van-button block round type="primary" :loading="adding" :disabled="!newUrl" @click="onAdd">
            添加
          </van-button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { showConfirmDialog, showSuccessToast } from 'vant'
import { getSmsStatus, getSmsMessages, sendSms, retrySms, deleteSms,
         addSmsGateway, removeSmsGateway } from '../../api/admin'

const status = ref({ enabled: false, reachable: false, gateway: '', gateways: [], pending: 0 })
const items = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const sending = ref(false)
const activeStatus = ref('')
const counts = ref({ all: 0, sent: 0, pending: 0, failed: 0 })
const form = ref({ phone: '', content: '' })
const addShow = ref(false)
const newUrl = ref('')
const adding = ref(false)

const gateways = computed(() => status.value.gateways || [])

const gateTip = computed(() => {
  if (!status.value.enabled) return '在服务器 .env 里设置 SMS_ENABLED=1 后重启后端'
  if (!gateways.value.length) return '未配置网关地址（SMS_GATEWAY_URL / SMS_GATEWAY_URL_2）'
  const online = gateways.value.filter((g) => g.reachable).length
  if (online === gateways.value.length) return `${online} 个监听窗口全部在线，按顺序优先使用`
  if (online > 0) return `${online}/${gateways.value.length} 个窗口在线，离线窗口的短信会走在线的那台`
  return '所有窗口都连不上 —— 短信会先存起来，手机回到网络后自动补发'
})

function statusText(s) {
  return s === 'sent' ? '已发送' : s === 'pending' ? '待发送' : '失败'
}
function statusType(s) {
  return s === 'sent' ? 'success' : s === 'pending' ? 'warning' : 'danger'
}

async function loadStatus() {
  try {
    status.value = await getSmsStatus()
  } catch (e) {
    /* 拦截器已提示 */
  }
}

function openAdd() {
  newUrl.value = ''
  addShow.value = true
}

async function onAdd() {
  const url = (newUrl.value || '').trim()
  if (!url) return
  adding.value = true
  try {
    await addSmsGateway(url)
    showSuccessToast('已添加监听窗口')
    addShow.value = false
    newUrl.value = ''
    await loadStatus()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    adding.value = false
  }
}

async function onRemove(gw) {
  try {
    await showConfirmDialog({
      title: '删除监听窗口',
      message: `确定删除 ${gw.url} 吗？`,
    })
  } catch (e) {
    return
  }
  try {
    await removeSmsGateway(gw.url)
    showSuccessToast('已删除')
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    await loadStatus()
  }
}

async function loadList(p = 1) {
  loading.value = true
  try {
    const res = await getSmsMessages({
      status: activeStatus.value || undefined,
      page: p,
      size: 20,
    })
    total.value = res?.total || 0
    counts.value = res?.counts || counts.value
    page.value = p
    items.value = p === 1 ? res?.items || [] : [...items.value, ...(res?.items || [])]
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

async function onSend() {
  try {
    await showConfirmDialog({
      title: '确认发送',
      message: `发送到 ${form.value.phone}？\n\n${form.value.content}`,
    })
  } catch (e) {
    return
  }
  sending.value = true
  try {
    await sendSms({ phone: form.value.phone, content: form.value.content })
    showSuccessToast('已发送')
    form.value.content = ''
    await Promise.all([loadStatus(), loadList(1)])
  } catch (e) {
    await Promise.all([loadStatus(), loadList(1)])
  } finally {
    sending.value = false
  }
}

async function onRetry(it) {
  try {
    await retrySms(it.id)
    showSuccessToast('已重发')
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    await Promise.all([loadStatus(), loadList(1)])
  }
}

async function onDelete(it) {
  try {
    await showConfirmDialog({ title: '删除记录', message: '删除后不可恢复，确定？' })
  } catch (e) {
    return
  }
  try {
    await deleteSms(it.id)
    showSuccessToast('已删除')
    await Promise.all([loadStatus(), loadList(1)])
  } catch (e) {
    /* 拦截器已提示 */
  }
}

onMounted(() => {
  loadStatus()
  loadList(1)
})
</script>

<style scoped>
.sms-page {
  min-height: 100vh;
  background: #f7f8fa;
  padding-bottom: 24px;
}
.page-head {
  display: flex;
  align-items: center;
  padding: 14px 16px 4px;
}
.page-title {
  font-size: 18px;
  font-weight: 600;
  color: #323233;
}
.head-add {
  margin-left: auto;
  font-size: 22px;
  color: #1989fa;
  padding: 4px;
}
.head-add:active {
  opacity: 0.6;
}
.gw-del {
  margin-left: auto;
  font-size: 14px;
  padding: 2px 4px;
  opacity: 0.85;
}
.add-box {
  padding: 18px 16px 8px;
}
.add-title {
  font-size: 16px;
  font-weight: 600;
  text-align: center;
  margin-bottom: 12px;
  color: #323233;
}
.add-tip {
  margin: 10px 4px 16px;
  font-size: 12px;
  color: #969799;
  line-height: 1.6;
}
.add-btns {
  display: flex;
  gap: 12px;
}
.gate-card {
  margin: 12px 16px;
  padding: 14px 16px;
  border-radius: 12px;
  color: #fff;
}
.gate-card.ok {
  background: linear-gradient(135deg, #07c160, #0aa651);
}
.gate-card.warn {
  background: linear-gradient(135deg, #ff976a, #f56c6c);
}
.gate-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gate-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.3);
}
.gate-title {
  font-size: 15px;
  font-weight: 600;
}
.pending-badge {
  margin-left: auto;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.24);
  padding: 2px 10px;
  border-radius: 999px;
}
.gate-tip {
  margin-top: 6px;
  font-size: 12px;
  opacity: 0.9;
  word-break: break-all;
}
.gate-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.gate-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.16);
  padding: 4px 10px;
  border-radius: 6px;
  word-break: break-all;
}
.gw-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.45);
  flex: 0 0 auto;
}
.gw-dot.on {
  background: #b7ffd2;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.35);
}
.gw-url {
  font-family: Menlo, Consolas, monospace;
  opacity: 0.95;
}
.list-head {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.msg-item {
  padding: 12px 16px;
  border-bottom: 1px solid #f2f3f5;
}
.msg-item:last-child {
  border-bottom: none;
}
.msg-top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.msg-phone {
  font-weight: 600;
  font-size: 15px;
  color: #323233;
}
.msg-content {
  margin-top: 6px;
  font-size: 14px;
  color: #323233;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
}
.msg-meta {
  margin-top: 6px;
  font-size: 12px;
  color: #969799;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.kind {
  color: #1989fa;
}
.msg-actions {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.msg-error {
  flex: 1;
  font-size: 12px;
  color: #ee0a24;
  word-break: break-all;
}
.msg-ok {
  font-size: 12px;
  color: #07c160;
}
.msg-btns {
  margin-left: auto;
  display: flex;
  gap: 8px;
}
</style>
