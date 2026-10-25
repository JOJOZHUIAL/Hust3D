<template>
  <div class="page admin page--wide">
    <van-nav-bar title="打印机监视" left-arrow fixed placeholder @click-left="$router.replace('/admin')">
      <template #right>
        <van-icon name="plus" size="20" @click="showAdd = true" />
      </template>
    </van-nav-bar>

    <div class="p-body">
      <van-empty v-if="!loading && list.length === 0" description="暂无打印机，点右上角 + 添加" />
      <!-- 打印机卡片 -->
      <div class="p-grid">
        <div
          v-for="p in list"
          :key="p.id"
          class="p-card"
          @click="$router.push(`/admin/printers/${p.id}`)"
        >
          <div class="p-head">
            <div class="p-icon" :class="p.online ? 'on' : 'off'">
              <van-icon name="printer" size="26" />
            </div>
            <span class="p-dot" :class="p.online ? 'on' : 'off'"></span>
          </div>
          <div class="p-name">{{ p.name }}</div>
          <div class="p-meta">
            <span class="p-state" :class="{ running: p.state === 'RUNNING' }">{{ p.state_text }}</span>
            <span v-if="p.percent != null && p.state === 'RUNNING'" class="p-percent">{{ p.percent }}%</span>
          </div>
          <div class="p-task">{{ taskOf(p) }}</div>
          <div v-if="actualsOf(p).length > 1" class="p-job">
            {{ actualsOf(p).length }} 份申请 · 进度 {{ progressOf(p) }}%
          </div>
          <div v-else-if="actualsOf(p).length === 1" class="p-job">
            申请 {{ actualsOf(p)[0].apply_no }} · 进度 {{ progressOf(p) }}%
          </div>
          <div v-else-if="assignmentsOf(p).length" class="p-job warn">
            已指派 {{ assignmentsOf(p).map((a) => a.apply_no).join("、") }}（等待开始）
          </div>
          <div class="p-ip">{{ p.ip }}</div>
          <van-button
            size="mini"
            plain
            type="danger"
            class="p-del"
            @click.stop="onDelete(p)"
          >
            删除
          </van-button>
        </div>
      </div>
    </div>

    <!-- 添加打印机 -->
    <van-popup v-model:show="showAdd" position="bottom" round :style="{ minHeight: '52%' }">
      <div class="add-panel">
        <div class="add-title">添加拓竹打印机</div>
        <van-cell-group inset>
          <van-field v-model="form.name" label="名称" placeholder="如：工作室 A1" maxlength="64" required />
          <van-field v-model="form.ip" label="IP 地址" placeholder="打印机的局域网 IP" maxlength="64" required />
          <van-field v-model="form.access_code" label="访问码" placeholder="打印机屏幕上显示的访问码" maxlength="64" required />
          <van-field v-model="form.serial" label="序列号" placeholder="选填，连接后自动发现" maxlength="64" />
        </van-cell-group>
        <div class="add-btns">
          <van-button block round plain @click="showAdd = false">取消</van-button>
          <van-button block round type="primary" :loading="saving" @click="onAdd">添加</van-button>
        </div>
        <p class="add-tip">
          提示：打印机需与服务器在同一局域网；访问码在打印机屏幕「设置 → 局域网访问」中查看。
        </p>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { showConfirmDialog, showSuccessToast, showFailToast } from 'vant'
import { getPrinterList, addPrinter, deletePrinter } from '../../api/printer'

const list = ref([])
const loading = ref(true)
const showAdd = ref(false)
const saving = ref(false)
const form = ref({ name: '', ip: '', access_code: '', serial: '' })
let timer = null

async function load() {
  try {
    list.value = await getPrinterList()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

// 卡片上显示打印机真实在打什么（优先打印机上报的 task_name）
function taskOf(p) {
  const task = p.job?.task || p.task_name || p.print_file
  if (task) return task
  return p.job?.assignments?.length ? '等待开始打印' : 'N/A'
}

function actualsOf(p) {
  return p.job?.actuals || []
}

function assignmentsOf(p) {
  return p.job?.assignments || []
}

function progressOf(p) {
  const a = actualsOf(p)[0]
  return a && a.progress != null ? a.progress : p.percent != null ? p.percent : 0
}

async function onAdd() {
  if (!form.value.name.trim() || !form.value.ip.trim() || !form.value.access_code.trim()) {
    showFailToast('请完整填写名称、IP 和访问码')
    return
  }
  saving.value = true
  try {
    await addPrinter({
      name: form.value.name.trim(),
      ip: form.value.ip.trim(),
      access_code: form.value.access_code.trim(),
      serial: form.value.serial.trim(),
    })
    showSuccessToast('添加成功，正在连接')
    form.value = { name: '', ip: '', access_code: '', serial: '' }
    showAdd.value = false
    load()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    saving.value = false
  }
}

async function onDelete(p) {
  try {
    await showConfirmDialog({
      title: '删除打印机',
      message: `确定删除「${p.name}」吗？删除后不再监视其状态。`,
    })
  } catch (e) {
    return
  }
  try {
    await deletePrinter(p.id)
    showSuccessToast('已删除')
    load()
  } catch (e) {
    /* 拦截器已提示 */
  }
}

onMounted(() => {
  load()
  timer = setInterval(() => {
    if (!document.hidden) load()
  }, 5000)
})

onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.p-body {
  padding-top: 10px;
}
.p-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
  padding: 0 16px;
}
.p-card {
  position: relative;
  background: #fff;
  border-radius: 16px;
  padding: 16px 14px 14px;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(20, 46, 104, 0.06);
}
.p-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.p-icon {
  width: 52px;
  height: 52px;
  border-radius: 16px;
  display: grid;
  place-items: center;
  color: #fff;
}
.p-icon.on {
  background: #07c160;
  box-shadow: 0 4px 14px rgba(7, 193, 96, 0.35);
}
.p-icon.off {
  background: #c8c9cc;
}
.p-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.p-dot.on {
  background: #07c160;
  box-shadow: 0 0 0 3px rgba(7, 193, 96, 0.18);
}
.p-dot.off {
  background: #c8c9cc;
}
.p-name {
  margin-top: 12px;
  font-size: 15px;
  font-weight: 600;
  color: #1a2233;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.p-meta {
  margin-top: 4px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.p-state {
  font-size: 12px;
  color: #969799;
}
.p-state.running {
  color: #ff976a;
  font-weight: 600;
}
.p-percent {
  font-size: 13px;
  font-weight: 700;
  color: #ff976a;
}
.p-task {
  margin-top: 2px;
  font-size: 11px;
  color: #646566;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.p-job {
  margin-top: 2px;
  font-size: 11px;
  font-weight: 600;
  color: #2f6bff;
}
.p-job.warn {
  color: #ff976a;
}
.p-ip {
  margin-top: 4px;
  font-size: 11px;
  color: #c8c9cc;
}
.p-del {
  margin-top: 8px;
}

.add-panel {
  padding: 18px 0 24px;
}
.add-title {
  text-align: center;
  font-size: 16px;
  font-weight: 600;
  color: #1a2233;
  margin-bottom: 14px;
}
.add-btns {
  display: flex;
  gap: 12px;
  margin: 16px 16px 0;
}
.add-tip {
  margin: 14px 20px 0;
  font-size: 12px;
  line-height: 1.7;
  color: #969799;
}

@media (min-width: 768px) {
  .p-grid {
    grid-template-columns: repeat(3, 1fr);
    padding: 0 36px;
  }
}
</style>
