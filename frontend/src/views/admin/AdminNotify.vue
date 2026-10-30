<template>
  <div class="msg-page">
    <van-nav-bar title="消息通知" left-arrow @click-left="$router.back()" />

    <div class="msg-wrap">
      <!-- 左：菜单 -->
      <div class="msg-menu">
        <div
          v-for="m in MENU"
          :key="m.key"
          class="menu-item"
          :class="{ on: tab === m.key }"
          @click="switchTab(m.key)"
        >
          <van-icon :name="m.icon" size="20" />
          <span>{{ m.label }}</span>
        </div>
      </div>

      <!-- 快速回复：点收件信息直接回信（短信走网关，邮件走 SMTP） -->
      <van-popup v-model:show="qrShow" position="bottom" round :style="{ minHeight: '46%' }">
        <div class="qr">
          <div class="qr-title">
            快速回复
            <van-tag :color="qr.channel === 'email' ? '#2f6bff' : '#1989fa'" round>
              {{ qr.channel === 'email' ? '邮件' : '短信' }}
            </van-tag>
          </div>
          <van-cell-group inset>
            <van-field v-model="qr.to" label="收件人" :placeholder="qr.channel === 'email' ? '收件邮箱' : '手机号'" />
            <van-field v-if="qr.channel === 'email'" v-model="qr.subject" label="主题" maxlength="120" placeholder="邮件主题" />
            <van-field
              v-model="qr.body"
              label="内容"
              type="textarea"
              rows="4"
              autosize
              :maxlength="qr.channel === 'sms' ? 500 : 10000"
              show-word-limit
              placeholder="回复内容"
            />
          </van-cell-group>
          <van-button block round type="primary" :loading="qrSending" @click="sendQuickReply">发送</van-button>
        </div>
      </van-popup>
      <!-- 左：内容区 -->
      <div class="msg-content">
        <!-- ① 收件 -->
        <div v-show="tab === 'inbox'" class="pane">
          <van-search
            v-model="keyword"
            placeholder="搜索联系人 / 内容 / 备注"
            shape="round"
            @update:model-value="onSearch"
            @clear="onSearch"
          />
          <!-- 通道切换：短信收件 / 邮件收件 -->
          <div class="ch">
            <button :class="{ on: inboxChannel === 'sms' }" type="button" @click="inboxChannel = 'sms'">短信</button>
            <button :class="{ on: inboxChannel === 'email' }" type="button" @click="switchEmailInbox">邮件</button>
          </div>
          <div class="pane-head">
            <span>收件箱<em v-if="total"> · {{ total }}</em></span>
            <van-icon name="replay" size="16" @click="loadInbox(true)" />
          </div>

          <van-empty v-if="inboxChannel === 'sms' && !loadingInbox && !inbox.length" image-size="56" description="没有匹配的短信" />
          <div v-show="inboxChannel === 'sms'" v-for="m in inbox" :key="m.id" class="item" @click="openQuickReply('sms', m)">
            <div class="item-top">
              <!-- 发件人姓名/备注在前，号码在后 -->
              <span class="who">{{ m.alias || '未知' }}</span>
              <span class="num">{{ m.sender }}</span>
              <span class="when">{{ shortTime(m.time) }}</span>
            </div>
            <div class="text">{{ m.text }}</div>
            <div v-if="m.code || m.blocked" class="foot">
              <van-tag v-if="m.code" type="primary" round @click.stop="copyCode(m)">
                验证码 {{ m.code }} · 点我复制
              </van-tag>
              <van-tag v-if="m.blocked" type="danger" round>已拦截</van-tag>
            </div>
          </div>
          <div v-if="inbox.length < total" class="more">
            <van-button size="small" plain round :loading="loadingInbox" @click="loadInbox(false)">
              加载更多
            </van-button>
          </div>

          <!-- 邮件收件（IMAP 拉取发件邮箱的收件箱） -->
          <template v-if="inboxChannel === 'email'">
            <div v-if="loadingEmailInbox" class="em-loading">
              <van-loading size="20">正在拉取邮件…</van-loading>
            </div>
            <van-empty v-else-if="!emailInbox.length" image-size="56" description="没有任何邮件" />
            <div v-for="(e, i) in emailInbox" :key="'em' + i" class="item" @click="openQuickReply('email', e)">
              <div class="item-top">
                <span class="who">{{ e.from }}</span>
                <span class="when">{{ e.date }}</span>
              </div>
              <div class="text">{{ e.subject }}</div>
              <div v-if="e.snippet" class="text snippet">{{ e.snippet }}</div>
            </div>
          </template>
        </div>

        <!-- ② 发送 -->
        <div v-show="tab === 'send'" class="pane">
          <van-cell-group inset :title="sendChannel === 'sms' ? '发送短信' : '发送邮件'">
            <!-- 联系人：输入姓名/手机/邮箱/学号关键字，下方列出匹配列表，点选自动填入 -->
            <van-field
              v-model="form.phone"
              label="联系人"
              type="tel"
              maxlength="11"
              placeholder="手机号 / 姓名关键字"
              @update:model-value="onContactInput"
            >
              <template #right-icon>
                <span v-if="matchName" class="stu-chip">{{ matchName }}</span>
              </template>
            </van-field>
            <template v-if="sendChannel === 'email'">
              <van-field
                v-model="emailForm.to"
                label="收件邮箱"
                placeholder="邮箱 / 姓名关键字"
                @update:model-value="onContactInput"
              >
                <template #right-icon>
                  <span v-if="matchName" class="stu-chip">{{ matchName }}</span>
                </template>
              </van-field>
              <van-field v-model="emailForm.subject" label="主题" maxlength="120" placeholder="邮件主题" />
            </template>
            <!-- 匹配列表：紧跟联系人字段下方（悬浮卡片） -->
            <div v-if="stuHits.length" class="stu-hits">
              <div v-for="u in stuHits" :key="u.id" class="stu-hit" @click="pickStudent(u)">
                <span class="stu-name">{{ u.name || u.student_id }}</span>
                <span class="stu-meta">
                  {{ u.phone || "无手机" }} · {{ u.email || "无邮箱" }} · {{ u.student_id }}
                </span>
              </div>
            </div>
            <van-field
              v-if="sendChannel === 'sms'"
              v-model="form.text"
              label="内容"
              type="textarea"
              rows="3"
              autosize
              maxlength="500"
              show-word-limit
              placeholder="短信内容"
            />
            <van-field
              v-else
              v-model="emailForm.body"
              label="内容"
              type="textarea"
              rows="5"
              autosize
              maxlength="10000"
              show-word-limit
              placeholder="邮件正文"
            />
            <van-cell>
              <van-button block round type="primary" :loading="sending" :disabled="!canSend" @click="onSend">
                发送
              </van-button>
            </van-cell>
          </van-cell-group>

          <!-- 通道切换：短信 / 邮件 -->
          <div class="ch">
            <button :class="{ on: sendChannel === 'sms' }" type="button" @click="sendChannel = 'sms'">短信</button>
            <button :class="{ on: sendChannel === 'email' }" type="button" @click="sendChannel = 'email'">邮件</button>
          </div>

          <div class="pane-head">
            <span>发送记录</span>
            <van-icon name="replay" size="16" @click="loadOutbound" />
          </div>
          <van-empty v-if="!sendMerged.length" image-size="56" description="还没有发送记录" />
          <div v-for="o in sendMerged" :key="o.channel + o.id" class="item">
            <div class="item-top">
              <span class="who">{{ o.channel === 'email' ? o.to : o.phone }}</span>
              <van-tag :color="o.channel === 'email' ? '#2f6bff' : '#1989fa'" round>
                {{ o.channel === 'email' ? '邮件' : '短信' }}
              </van-tag>
              <van-tag v-if="o.channel === 'email'" :type="o.status === 'sent' ? 'success' : 'danger'" round>
                {{ o.status === 'sent' ? '已发送' : '失败' }}
              </van-tag>
              <van-tag v-else :type="o.status === 'sent' ? 'success' : o.status === 'give_up' ? 'danger' : 'warning'" round>
                {{ o.status_text }}
              </van-tag>
              <span class="when">{{ shortTime(o.time) }}</span>
            </div>
            <div class="text">{{ o.channel === 'email' ? `【${o.subject}】${o.body || ''}` : o.text }}</div>
            <div v-if="o.error" class="err">{{ o.error }}</div>
          </div>
        </div>

        <!-- ③ 状态 -->
        <div v-show="tab === 'status'" class="pane">
          <div class="st-card" :class="{ off: !st.online }">
            <div class="st-main">
              <span class="st-dot" />
              <span class="st-title">{{ st.online ? '设备在线' : '设备离线' }}</span>
              <span class="st-ago">{{ st.last_seen }}</span>
            </div>
            <div class="st-row">
              <span>信号
                <b>{{ '▮'.repeat(st.signal || 0) }}{{ '▯'.repeat(4 - (st.signal || 0)) }}</b>
                <i>{{ st.signal_text }}</i>
              </span>
              <span>号码 <b>{{ st.sim_number }}</b></span>
            </div>
          </div>

          <van-cell-group inset title="自动识别到的卡">
            <van-cell
              v-for="s in st.sims || []"
              :key="s.sim_id"
              :title="s.number"
              :label="s.operator"
            >
              <template #value>
                <van-tag :type="s.online ? 'success' : 'default'" round>
                  {{ s.online ? '在用' : '未接入' }}
                </van-tag>
              </template>
            </van-cell>
            <van-cell v-if="!(st.sims || []).length" title="暂无可用 SIM 卡" />
          </van-cell-group>

          <!-- 设备与网络 -->
          <van-cell-group inset title="设备与网络">
            <div class="kv-grid">
              <div v-for="kv in deviceRows" :key="kv.k" class="kv">
                <span class="kv-k">{{ kv.k }}</span>
                <span class="kv-v">{{ kv.v || '—' }}</span>
              </div>
            </div>
          </van-cell-group>

          <!-- 同步与计数 -->
          <van-cell-group inset title="同步与收发">
            <div class="kv-grid">
              <div v-for="kv in syncRows" :key="kv.k" class="kv">
                <span class="kv-k">{{ kv.k }}</span>
                <span class="kv-v">{{ kv.v }}</span>
              </div>
            </div>
          </van-cell-group>

          <div class="pane-head" style="padding-top: 14px">
            <span>固件日志</span>
            <span>
              <van-button size="mini" plain round :loading="pulling" @click="onPull">强制拉取</van-button>
              <van-button size="mini" plain round :loading="logLoading" @click="loadLog">刷新日志</van-button>
            </span>
          </div>
          <div class="log-box">
            <div v-if="!logLines.length" class="log-empty">暂无日志（设备离线或日志已清空）</div>
            <div v-for="(l, i) in logLines" :key="i" class="log-line">{{ l.text }}</div>
          </div>
          <p class="hint">卡片由设备自动上报，无需手动添加；插卡后设备下次心跳即可识别。</p>
        </div>

        <!-- ④ 设置 -->
        <div v-show="tab === 'settings'" class="pane">
          <van-cell-group inset title="自动通知">
            <van-cell title="自动短信" label="打印完成时自动给申请人发取件短信">
              <template #right-icon>
                <van-switch v-model="autoSms" size="22" @change="saveFlags" />
              </template>
            </van-cell>
            <van-cell title="自动邮件" label="打印完成时自动发邮件（SMTP 已配置时生效）">
              <template #right-icon>
                <van-switch v-model="autoEmail" size="22" @change="saveFlags" />
              </template>
            </van-cell>
          </van-cell-group>
          <p class="hint">开关保存后立即生效，并写入服务器 .env（重启也不会丢）。</p>

          <van-cell-group inset title="发送模板">
            <van-field
              v-model="tpl.sms"
              label="短信"
              type="textarea"
              rows="3"
              autosize
              maxlength="300"
              show-word-limit
              placeholder="【3D打印服务】{name}同学，您的打印件（{apply_no}）已打印完成…"
            />
            <van-field
              v-model="tpl.email_subject"
              label="邮件主题"
              maxlength="120"
              placeholder="【3D打印服务】你的打印件已完成，请领取"
            />
            <van-field
              v-model="tpl.email_body"
              label="邮件正文"
              type="textarea"
              rows="6"
              autosize
              maxlength="2000"
              show-word-limit
              placeholder="{name} 同学：\n\n你提交的申请（{apply_no}）已打印完成…"
            />
          </van-cell-group>

          <van-cell-group inset title="反馈提醒模板（7 天内未过期 / 已过期）">
            <van-field
              v-model="tpl.sms_remind"
              label="未过期短信"
              type="textarea"
              rows="3"
              autosize
              maxlength="300"
              show-word-limit
              placeholder="【3D打印服务】{name}同学，你的打印件（{apply_no}）已完成 {days} 天还未收到反馈…"
            />
            <van-field
              v-model="tpl.sms_remind_expired"
              label="已过期短信"
              type="textarea"
              rows="3"
              autosize
              maxlength="300"
              show-word-limit
              placeholder="【3D打印服务】{name}同学，你的打印件（{apply_no}）反馈已超过 {days} 天期限…"
            />
            <van-field
              v-model="tpl.email_remind_subject"
              label="提醒邮件主题"
              maxlength="120"
              placeholder="【3D打印服务】反馈提醒：申请 {apply_no}"
            />
            <van-field
              v-model="tpl.email_remind_body"
              label="提醒邮件正文"
              type="textarea"
              rows="5"
              autosize
              maxlength="2000"
              show-word-limit
              placeholder="{name} 同学：你提交的申请（{apply_no}）{state}…"
            />
            <van-cell>
              <van-button block round type="primary" :loading="savingTpl" @click="onSaveTemplates">
                保存模板
              </van-button>
            </van-cell>
          </van-cell-group>
          <p class="hint">
            可用占位符：<b v-for="p in tpl.placeholders || []" :key="p" class="ph">{{ p }}</b>
            <br />{days}=完成天数、{state}=未过期/已过期描述、{deadline}=反馈截止时间。
            <br />改完点保存立即生效；正文可以换行，换行会被原样发送。
          </p>
        </div>
      </div>

      <!-- 快速回复：点收件信息直接回信（短信走网关，邮件走 SMTP） -->
      <van-popup v-model:show="qrShow" position="bottom" round :style="{ minHeight: '46%' }">
        <div class="qr">
          <div class="qr-title">
            快速回复
            <van-tag :color="qr.channel === 'email' ? '#2f6bff' : '#1989fa'" round>
              {{ qr.channel === 'email' ? '邮件' : '短信' }}
            </van-tag>
          </div>
          <van-cell-group inset>
            <van-field v-model="qr.to" label="收件人" :placeholder="qr.channel === 'email' ? '收件邮箱' : '手机号'" />
            <van-field v-if="qr.channel === 'email'" v-model="qr.subject" label="主题" maxlength="120" placeholder="邮件主题" />
            <van-field
              v-model="qr.body"
              label="内容"
              type="textarea"
              rows="4"
              autosize
              :maxlength="qr.channel === 'sms' ? 500 : 10000"
              show-word-limit
              placeholder="回复内容"
            />
          </van-cell-group>
          <van-button block round type="primary" :loading="qrSending" @click="sendQuickReply">发送</van-button>
        </div>
      </van-popup>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { showSuccessToast, showFailToast } from 'vant'
import {
  getNativeSmsStatus, getNativeSmsMessages, getNativeSmsOutbound, sendNativeSms,
  getNativeSmsSettings, saveNativeSmsSettings, getNativeSmsLog, pullNativeSms,
  sendEmail, getEmailList, getEmailInbox, searchUsers,
} from '../../api/admin'

const MENU = [
  { key: 'inbox', label: '收件', icon: 'envelop-o' },
  { key: 'send', label: '发送', icon: 'guide-o' },
  { key: 'status', label: '状态', icon: 'chart-trending-o' },
  { key: 'settings', label: '设置', icon: 'setting-o' },
]

// —— 通道：收件（短信/邮件）与发送（短信/邮件） ——
const inboxChannel = ref('sms')
const sendChannel = ref('sms')

// —— 联系人自动补全：输入姓名/手机/邮箱/学号 → 匹配学生，唯一命中自动填入并显示姓名徽章 ——
const stuHits = ref([])
const matchName = ref('')
let stuTimer = null

function onContactInput() {
  clearTimeout(stuTimer)
  const kw = (form.value.phone || '').trim() || (emailForm.value.to || '').trim()
  matchName.value = ''
  if (kw.length < 1) {
    stuHits.value = []
    return
  }
  stuTimer = setTimeout(async () => {
    try {
      stuHits.value = await searchUsers(kw)
    } catch (e) {
      stuHits.value = []
    }
  }, 300)
}

function applyStudent(u) {
  if (u.phone) form.value.phone = u.phone
  if (u.email) emailForm.value.to = u.email
  matchName.value = u.name || u.student_id || ''
}

function pickStudent(u) {
  applyStudent(u)
  stuHits.value = []
}
const emailInbox = ref([])
const loadingEmailInbox = ref(false)
const emailOut = ref([]) // 邮件发送记录
const emailForm = ref({ to: '', subject: '', body: '' })

// 快速回复弹窗
const qrShow = ref(false)
const qrSending = ref(false)
const qr = ref({ channel: 'sms', to: '', subject: '', body: '' })

const EMAIL_RE = /[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/

function extractEmail(s) {
  const m = (s || '').match(EMAIL_RE)
  return m ? m[0] : ''
}

function openQuickReply(channel, item) {
  if (channel === 'sms') {
    qr.value = { channel: 'sms', to: item.sender || '', subject: '', body: '' }
  } else {
    const to = extractEmail(item.from)
    if (!to) {
      showFailToast('未能识别对方邮箱，请手动填写')
    }
    qr.value = {
      channel: 'email',
      to,
      subject: /^re:/i.test(item.subject || '') ? item.subject : 'Re: ' + (item.subject || ''),
      body: '',
    }
  }
  qrShow.value = true
}

async function sendQuickReply() {
  const q = qr.value
  if (!q.to.trim()) {
    showFailToast(q.channel === 'email' ? '请填写收件邮箱' : '请填写收件人手机号')
    return
  }
  if (!q.body.trim()) {
    showFailToast('请填写回复内容')
    return
  }
  qrSending.value = true
  try {
    if (q.channel === 'sms') {
      await sendNativeSms({ phone: q.to.trim(), text: q.body.trim() })
      showSuccessToast('短信已提交发送')
      loadOutbound()
    } else {
      await sendEmail({ to: q.to.trim(), subject: q.subject.trim() || '（无主题）', body: q.body })
      showSuccessToast('邮件已发送')
      loadEmailOutbound()
    }
    qrShow.value = false
    qr.value = { channel: q.channel, to: '', subject: '', body: '' }
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    qrSending.value = false
  }
}

async function loadEmailInbox() {
  loadingEmailInbox.value = true
  try {
    const d = await getEmailInbox()
    emailInbox.value = d?.items || []
  } catch (e) {
    emailInbox.value = []
  } finally {
    loadingEmailInbox.value = false
  }
}

function switchEmailInbox() {
  // 必须先切通道再拉取：原实现只拉取、不切通道，点"邮件"看起来毫无反应
  inboxChannel.value = 'email'
  if (!emailInbox.value.length) loadEmailInbox()
}

async function loadEmailOutbound() {
  try {
    emailOut.value = await getEmailList()
  } catch (e) {
    /* 静默 */
  }
}

const tab = ref('inbox')
const st = ref({ online: false, signal: 0, signal_text: '未知', sim_number: '未上报', sims: [] })

const keyword = ref('')
const inbox = ref([])
const total = ref(0)
const loadingInbox = ref(false)
let searchTimer = null

const form = ref({ phone: '', text: '' })
const sending = ref(false)
const outbound = ref([])

const autoSms = ref(true)
const autoEmail = ref(true)
const tpl = ref({
  sms: '', email_subject: '', email_body: '',
  sms_remind: '', sms_remind_expired: '',
  email_remind_subject: '', email_remind_body: '',
  placeholders: [],
})
const logLines = ref([])
const logLoading = ref(false)
const pulling = ref(false)

const deviceRows = computed(() => {
  const d = st.value.detail || {}
  const m = d.modem || {}
  return [
    { k: '设备 MAC', v: d.mac },
    { k: '设备 IP', v: d.ip },
    { k: '固件版本', v: d.fw ? 'v' + d.fw : '' },
    { k: '模组型号', v: m.model },
    { k: '注册状态', v: m.registered },
    { k: '信号', v: m.signal_dbm != null ? m.signal_dbm + ' dBm（' + m.signal_text + '）' : '' },
    { k: '运营商', v: m.operator },
    { k: 'IMSI 尾号', v: m.imsi_tail },
    { k: 'ICCID 尾号', v: m.iccid_tail },
    { k: '数据连接', v: m.data ? '已连接' : '未连接' },
    { k: 'WiFi', v: d.wifi_ssid ? d.wifi_ssid + (d.wifi_rssi ? '（' + d.wifi_rssi + ' dBm）' : '') : '' },
    { k: '运行时长', v: d.uptime },
    { k: '可用内存', v: d.free_heap_kb ? d.free_heap_kb + ' KB' : '' },
    { k: '复位原因', v: d.reset_reason },
  ]
})

const syncRows = computed(() => {
  const s = st.value.sync || {}
  const c = st.value.counters || {}
  return [
    { k: '本地已收', v: s.local_received ?? '—' },
    { k: '本地已发', v: s.local_sent ?? '—' },
    { k: '设备收/发', v: (c.rx ?? '—') + ' / ' + (c.tx ?? '—') },
    { k: '游标', v: s.cursor ?? '—' },
    { k: '设备缓冲', v: (s.buffer_used ?? 0) + ' / ' + (s.buffer_capacity ?? 50) },
    { k: '上次拉取', v: s.last_poll || '—' },
    { k: '上次上报', v: s.last_hook || '—' },
  ]
})
const savingTpl = ref(false)

const canSend = computed(() => /^1\d{10}$/.test(form.value.phone) && form.value.text.trim().length > 0)

function shortTime(t) {
  return t ? (t.length > 16 ? t.slice(5, 16) : t) : ''
}

async function loadStatus() {
  try {
    const d = await getNativeSmsStatus()
    st.value = d
    autoSms.value = !!d.auto_sms
    autoEmail.value = !!d.auto_email
  } catch (e) {
    /* 拦截器已提示 */
  }
}

async function loadInbox(reset = false) {
  loadingInbox.value = true
  try {
    const params = { limit: 50, keyword: keyword.value.trim() || undefined }
    if (!reset && inbox.value.length) params.before_id = inbox.value[inbox.value.length - 1].id
    const res = await getNativeSmsMessages(params)
    total.value = res?.total || 0
    inbox.value = reset ? res?.items || [] : [...inbox.value, ...(res?.items || [])]
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loadingInbox.value = false
  }
}

function onSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => loadInbox(true), 300)
}

async function loadOutbound() {
  try {
    const res = await getNativeSmsOutbound({ limit: 50 })
    outbound.value = res?.items || []
  } catch (e) {
    /* 拦截器已提示 */
  }
  loadEmailOutbound()
}

// 短信 + 邮件发送记录合并（通道标签区分，按时间倒序）
const sendMerged = computed(() => {
  const merged = [
    ...outbound.value.map((o) => ({ ...o, channel: 'sms', time: o.time || o.created_at || '' })),
    ...emailOut.value.map((e) => ({ ...e, channel: 'email', time: e.created_at || '' })),
  ]
  return merged.sort((a, b) => String(b.time).localeCompare(String(a.time)))
})

async function loadLog() {
  logLoading.value = true
  try {
    const res = await getNativeSmsLog(0)
    logLines.value = (res?.lines || []).slice(-80)
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    logLoading.value = false
  }
}

async function onPull() {
  pulling.value = true
  try {
    const res = await pullNativeSms()
    showSuccessToast(`已拉取，新增 ${res?.new_messages ?? 0} 条`)
    await Promise.all([loadStatus(), loadInbox(true), loadLog()])
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    pulling.value = false
  }
}

async function onSend() {
  sending.value = true
  try {
    if (sendChannel.value === 'email') {
      const f = emailForm.value
      if (!f.to.trim()) { showFailToast('请填写收件邮箱'); return }
      if (!f.subject.trim()) { showFailToast('请填写邮件主题'); return }
      if (!f.body.trim()) { showFailToast('请填写邮件正文'); return }
      await sendEmail({ to: f.to.trim(), subject: f.subject.trim(), body: f.body })
      showSuccessToast('邮件已发送')
      f.to = ''; f.subject = ''; f.body = ''
      loadEmailOutbound()
    } else {
      await sendNativeSms({ phone: form.value.phone, text: form.value.text.trim() })
      showSuccessToast('已提交发送')
      form.value.text = ''
      loadOutbound()
    }
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    sending.value = false
  }
}

async function loadTemplates() {
  try {
    const s = await getNativeSmsSettings()
    if (s?.templates) tpl.value = s.templates
  } catch (e) {
    /* 拦截器已提示 */
  }
}

async function onSaveTemplates() {
  if (!tpl.value.sms.trim() || !tpl.value.email_body.trim() || !tpl.value.email_subject.trim()) {
    showFailToast('短信、邮件主题、邮件正文都不能为空')
    return
  }
  savingTpl.value = true
  try {
    const res = await saveNativeSmsSettings({
      templates: {
        sms: tpl.value.sms,
        email_subject: tpl.value.email_subject,
        email_body: tpl.value.email_body,
        sms_remind: tpl.value.sms_remind,
        sms_remind_expired: tpl.value.sms_remind_expired,
        email_remind_subject: tpl.value.email_remind_subject,
        email_remind_body: tpl.value.email_remind_body,
      },
    })
    if (res?.templates) tpl.value = res.templates
    showSuccessToast('模板已保存')
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    savingTpl.value = false
  }
}

async function saveFlags() {
  try {
    await saveNativeSmsSettings({ auto_sms: autoSms.value, auto_email: autoEmail.value })
    showSuccessToast('已保存')
  } catch (e) {
    loadStatus()
  }
}

async function copyCode(m) {
  if (!m.code) return
  try {
    await navigator.clipboard.writeText(m.code)
    showSuccessToast(`已复制 ${m.code}`)
  } catch (e) {
    showFailToast('复制失败，请手动选择')
  }
}

function switchTab(key) {
  tab.value = key
  if (key === 'inbox' && !inbox.value.length) loadInbox(true)
  if (key === 'inbox' && inboxChannel.value === 'email' && !emailInbox.value.length) loadEmailInbox()
  if (key === 'send' && !outbound.value.length) loadOutbound()
  if (key === 'status') {
    loadStatus()
    loadLog()
  }
  if (key === 'settings') {
    loadStatus()
    loadTemplates()
  }
}

onMounted(() => {
  loadStatus()
  loadInbox(true)
})
</script>

<style scoped>
.msg-page {
  min-height: 100vh;
  background: #f7f8fa;
  display: flex;
  flex-direction: column;
}
.msg-wrap {
  flex: 1;
  display: flex;
  align-items: stretch;
  /* 左菜单 + 右内容 */
}
.msg-content {
  flex: 1;
  min-width: 0;
  padding-bottom: 24px;
  overflow-x: hidden;
}

/* —— 右侧竖向菜单 —— */
.msg-menu {
  flex: 0 0 64px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 6px;
  background: #fff;
  border-right: 1px solid #ebedf0;
  position: sticky;
  top: 0;
  height: calc(100vh - 46px);
}
.menu-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 10px 2px;
  border-radius: 10px;
  color: #646566;
  font-size: 11px;
  line-height: 1.2;
  cursor: pointer;
}
.menu-item.on {
  color: #1989fa;
  background: #eef4ff;
  font-weight: 600;
}
.menu-item:active {
  background: #f2f3f5;
}

/* —— 通道切换 chips（短信 / 邮件） —— */
.ch {
  display: flex;
  gap: 8px;
  padding: 0 16px 10px;
}
.ch button {
  border: 1px solid #e5e9f2;
  background: #fff;
  color: #4e5566;
  border-radius: 999px;
  padding: 5px 16px;
  font-size: 12px;
  cursor: pointer;
}
.ch button.on {
  background: #2f6bff;
  border-color: #2f6bff;
  color: #fff;
  font-weight: 600;
}
.em-loading {
  display: flex;
  justify-content: center;
  padding: 28px 0;
  color: #969799;
}
.text.snippet {
  color: #969799;
  font-size: 12px;
}

/* —— 学生搜索下拉 —— */
.stu-search {
  padding: 0 16px 4px;
}
.stu-hits {
  margin: -6px 16px 10px;
  border: 1px solid #e5e9f2;
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
  box-shadow: 0 8px 20px rgba(20, 46, 104, 0.12);
}
.stu-hit {
  padding: 10px 14px;
  border-bottom: 1px solid #f2f3f5;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.stu-hit:last-child {
  border-bottom: none;
}
.stu-hit:active {
  background: #f2f6ff;
}
.stu-hit:last-child {
  border-bottom: none;
}
.stu-hit:active {
  background: #fafafa;
}
.stu-name {
  font-size: 14px;
  color: #323233;
  font-weight: 600;
}
.stu-meta {
  font-size: 12px;
  color: #969799;
}

/* —— 列表 —— */
.pane {
  padding-top: 4px;
}
.pane-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px 6px;
  font-size: 13px;
  color: #646566;
}
.pane-head em {
  font-style: normal;
  color: #969799;
}
.item {
  padding: 10px 16px;
  background: #fff;
  border-bottom: 1px solid #f2f3f5;
}
.item:active {
  background: #fafafa;
}
.item-top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.who {
  font-size: 14px;
  font-weight: 600;
  color: #323233;
}
.num {
  font-size: 12px;
  color: #969799;
  font-family: Menlo, Consolas, monospace;
}
.num::before {
  content: '·';
  margin-right: 4px;
}
.when {
  margin-left: auto;
  font-size: 12px;
  color: #969799;
}
.text {
  margin-top: 5px;
  font-size: 14px;
  color: #323233;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
}
.foot {
  margin-top: 7px;
  display: flex;
  gap: 8px;
}
.err {
  margin-top: 4px;
  font-size: 12px;
  color: #ee0a24;
}
.more {
  padding: 12px 0;
  text-align: center;
}
.ph {
  display: inline-block;
  margin: 2px 6px 0 0;
  padding: 1px 6px;
  border-radius: 4px;
  background: #eef4ff;
  color: #1989fa;
  font-weight: 500;
}
.hint {
  margin: 10px 18px 0;
  font-size: 12px;
  color: #969799;
  line-height: 1.6;
}

/* —— 状态详情网格 —— */
.kv-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 12px;
  padding: 12px 16px 14px;
}
.kv {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.kv-k {
  font-size: 12px;
  color: #969799;
}
.kv-v {
  font-size: 13px;
  color: #323233;
  font-weight: 500;
  word-break: break-all;
}
.log-box {
  margin: 0 16px;
  padding: 10px 12px;
  background: #1e1e1e;
  border-radius: 8px;
  max-height: 260px;
  overflow: auto;
}
.log-line {
  font-family: Menlo, Consolas, monospace;
  font-size: 11px;
  line-height: 1.65;
  color: #d4d4d4;
  white-space: pre-wrap;
  word-break: break-all;
}
.log-empty {
  font-size: 12px;
  color: #969799;
  text-align: center;
  padding: 8px 0;
}

/* —— 状态卡 —— */
.st-card {
  margin: 12px 16px;
  padding: 14px 16px;
  border-radius: 12px;
  color: #fff;
  background: linear-gradient(135deg, #07c160, #0aa651);
}
.st-card.off {
  background: linear-gradient(135deg, #ff976a, #f56c6c);
}
.st-main {
  display: flex;
  align-items: center;
  gap: 8px;
}
.st-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.3);
}
.st-title {
  font-size: 15px;
  font-weight: 600;
}
.st-ago {
  margin-left: auto;
  font-size: 12px;
  opacity: 0.85;
}
.st-row {
  display: flex;
  gap: 18px;
  margin-top: 10px;
  font-size: 12px;
  opacity: 0.95;
}
.st-row b {
  font-family: Menlo, Consolas, monospace;
  letter-spacing: 1px;
}
.st-row i {
  font-style: normal;
  opacity: 0.8;
  margin-left: 4px;
}
</style>
