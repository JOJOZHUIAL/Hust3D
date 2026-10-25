<template>
  <van-popup v-model:show="show" position="bottom" round :style="{ maxHeight: '86%' }">
    <div class="pp">
      <div class="pp-title">开始打印</div>

      <div class="pp-app">
        <div class="pp-no">{{ app?.apply_no || '—' }}</div>
        <div class="pp-file">模型文件：{{ app?.file_name || '—' }}</div>
        <div class="pp-file">申请人：{{ app?.applicant?.name || '—' }}</div>
      </div>

      <van-radio-group v-if="printers.length" v-model="picked">
        <van-cell-group inset>
          <van-cell
            v-for="p in printers"
            :key="p.id"
            clickable
            @click="picked = p.id"
          >
            <template #title>
              <span class="pp-name">{{ p.name }}</span>
              <van-tag
                v-if="isBusy(p)"
                type="warning"
                style="margin-left: 6px"
              >占用中</van-tag>
              <van-tag v-else :type="p.online ? 'success' : 'default'" style="margin-left: 6px">
                {{ p.online ? '在线' : '离线' }}
              </van-tag>
            </template>
            <template #label>
              <span>{{ p.ip }}</span>
              <span v-if="isBusy(p)"> · 正在打印 {{ busyLabel(p) }}</span>
              <span v-else-if="p.state_text"> · {{ p.state_text }}</span>
            </template>
            <template #right-icon>
              <van-radio :name="p.id" @click.stop="picked = p.id" />
            </template>
          </van-cell>
        </van-cell-group>
      </van-radio-group>

      <van-empty v-else image-size="56" description="还没有添加打印机" />

      <p class="pp-tip">
        选中打印机后系统会把它与该申请绑定：打印机状态页会显示「正在打印该申请的 STL」，
        并自动监视进度，打印到 100% 时自动标记为已完成。
        <template v-if="!printers.length">
          未绑定打印机也可以开始打印，只是只能手动点「标记完成」。
        </template>
      </p>

      <div class="pp-btns">
        <van-button round plain block @click="show = false">取消</van-button>
        <van-button round type="primary" block :loading="saving" @click="onOk">
          开始打印
        </van-button>
      </div>
    </div>
  </van-popup>
</template>

<script setup>
import { ref } from 'vue'
import { showSuccessToast } from 'vant'
import { getPrinterList } from '../api/printer'
import { updateApplicationStatus } from '../api/admin'

const emit = defineEmits(['success'])

const show = ref(false)
const app = ref(null)
const printers = ref([])
const picked = ref(null)
const saving = ref(false)

// 这台打印机当前是否正在打本系统的申请（一盘多件时可能多份）
function isBusy(p) {
  return (p.job?.actuals || []).length > 0
}

function busyLabel(p) {
  const rows = p.job?.actuals || []
  if (rows.length > 1) return `${rows.length} 份申请`
  return rows[0]?.apply_no || "—"
}

// 父组件调用：picker.value.open(application)
async function open(target) {
  app.value = target
  picked.value = null
  show.value = true
  saving.value = false
  try {
    const rows = await getPrinterList()
    printers.value = rows || []
    // 只有一台空闲打印机时默认选中，减少一次点击
    const free = printers.value.filter((p) => !isBusy(p))
    if (free.length === 1) picked.value = free[0].id
  } catch (e) {
    printers.value = []
  }
}

async function onOk() {
  saving.value = true
  try {
    await updateApplicationStatus({
      id: app.value.id,
      status: 'printing',
      printer_id: picked.value || undefined,
    })
    showSuccessToast(picked.value ? '已开始打印，正在监视进度' : '已开始打印')
    show.value = false
    emit('success')
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    saving.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.pp {
  padding: 18px 0 22px;
}
.pp-title {
  text-align: center;
  font-size: 16px;
  font-weight: 600;
  color: #1a2233;
  margin-bottom: 12px;
}
.pp-app {
  margin: 0 20px 12px;
  padding: 12px 14px;
  border-radius: 10px;
  background: #f2f6ff;
}
.pp-no {
  font-size: 14px;
  font-weight: 600;
  color: #2f6bff;
}
.pp-file {
  margin-top: 4px;
  font-size: 12px;
  color: #646566;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pp-name {
  font-size: 14px;
  font-weight: 600;
  color: #1a2233;
}
.pp-tip {
  margin: 12px 20px 0;
  font-size: 12px;
  line-height: 1.7;
  color: #969799;
}
.pp-btns {
  display: flex;
  gap: 12px;
  margin: 16px 16px 0;
}
</style>
