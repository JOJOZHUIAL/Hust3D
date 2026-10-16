<template>
  <div class="page list">
    <van-nav-bar title="我的申请" left-arrow fixed placeholder @click-left="$router.back()" />

    <van-tabs v-model:active="activeTab" sticky @change="onTabChange">
      <van-tab v-for="t in TABS" :key="t.value" :title="t.label" :name="t.value" />
    </van-tabs>

    <!-- 日期筛选（chips 自动换行 + 日历范围） -->
    <div class="date-filter">
      <button
        v-for="c in dateChips"
        :key="c.key"
        class="d-chip"
        :class="{ active: dateMode === c.key }"
        type="button"
        @click="pickRange(c.key)"
      >
        {{ c.label }}
      </button>
      <button
        class="d-chip"
        :class="{ active: dateMode === 'custom' }"
        type="button"
        @click="calShow = true"
      >
        {{ customLabel }}
      </button>
    </div>

    <!-- 批量导出条 -->
    <div v-if="dateFiltered.length" class="batch-bar">
      <span class="batch-info">当前筛选 {{ dateFiltered.length }} 份</span>
      <van-button size="small" type="primary" icon="description" round :loading="exporting" @click="onBatchExport">
        批量导出 Word
      </van-button>
    </div>

    <div class="list-body">
      <van-empty v-if="!loading && dateFiltered.length === 0" description="暂无申请记录" />
      <van-cell-group v-else inset>
        <van-cell
          v-for="item in dateFiltered"
          :key="item.id"
          :title="item.apply_no"
          :label="`${PURPOSE_TEXT[item.purpose] || item.purpose} · ${item.created_at}`"
          is-link
          @click="$router.push(`/application/${item.id}`)"
        >
          <template #value>
            <van-tag :color="STATUS[item.status]?.color">{{ STATUS[item.status]?.text }}</van-tag>
            <van-tag v-if="item.feedback_url && item.feedback_reviewed === false" color="#ffd21e">反馈审核中</van-tag>
            <van-tag v-else-if="item.feedback_url && item.feedback_reviewed !== 2" color="#07c160">已反馈</van-tag>
            <van-tag v-else-if="item.status === 'completed'" color="#ff976a">未反馈</van-tag>
          </template>
        </van-cell>
      </van-cell-group>
    </div>

    <TabBar />

    <!-- 自定义日期范围 -->
    <van-calendar
      v-model:show="calShow"
      type="range"
      allow-same-day
      title="选择日期范围"
      :min-date="calMinDate"
      :max-date="calMaxDate"
      @confirm="onCalConfirm"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { getMyApplications, exportBatchApplication } from '../api/application'
import { downloadBlob } from '../api/application'
import TabBar from '../components/TabBar.vue'
import { STATUS, PURPOSE_TEXT } from '../utils/constants'

const TABS = [
  { value: '', label: '全部' },
  { value: 'pending', label: '待审批' },
  { value: 'approved', label: '已通过' },
  { value: 'printing', label: '打印中' },
  { value: 'completed', label: '已完成' },
  { value: 'rejected', label: '已拒绝' },
  { value: 'cancelled', label: '已取消' },
]

const activeTab = ref('')
const list = ref([])
const loading = ref(false)

// —— 日期筛选：近三天/近七天/近30天/近半年/近一年 + 日历自定义 ——
const DAY = 86400000
const dateMode = ref('all')
const customRange = ref(null) // [Date, Date]
const calShow = ref(false)
const calMinDate = new Date(2020, 0, 1)
const calMaxDate = new Date(Date.now() + 365 * DAY)

const dateChips = [
  { key: 'all', label: '全部' },
  { key: '3d', label: '近三天' },
  { key: '7d', label: '近七天' },
  { key: '30d', label: '近30天' },
  { key: '6m', label: '近半年' },
  { key: '1y', label: '近一年' },
]

const customLabel = computed(() => {
  if (dateMode.value !== 'custom' || !customRange.value) return '📅 日历选择'
  const p = (d) => `${String(d.getMonth() + 1).padStart(2, '0')}.${String(d.getDate()).padStart(2, '0')}`
  return `📅 ${p(customRange.value[0])} - ${p(customRange.value[1])}`
})

// 日期范围 → [start, end]（start 归零到当天 00:00）
function rangeOf(mode) {
  const now = new Date()
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const map = {
    '3d': 3, '7d': 7, '30d': 30,
    '6m': 182, '1y': 365,
  }
  if (map[mode]) return [new Date(start.getTime() - (map[mode] - 1) * DAY), now]
  if (mode === 'custom' && customRange.value) {
    const [a, b] = customRange.value
    return [new Date(a.getFullYear(), a.getMonth(), a.getDate()), b]
  }
  return null
}

function pickRange(key) {
  dateMode.value = key
  if (key === 'custom') {
    calShow.value = true
  }
}

function onCalConfirm(range) {
  customRange.value = range
  dateMode.value = 'custom'
  calShow.value = false
}

// 状态 tab ∩ 日期范围 双重过滤
const dateFiltered = computed(() => {
  let arr = list.value
  const range = dateMode.value === 'all' ? null : rangeOf(dateMode.value)
  if (range) {
    const [start, end] = range
    arr = arr.filter((x) => {
      const t = new Date((x.created_at || '').replace(/-/g, '/')).getTime()
      return t >= start.getTime() && t <= end.getTime() + DAY - 1
    })
  }
  return arr
})

// —— 批量导出 Word（合并为一份文档，每份申请一页） ——
const exporting = ref(false)

async function onBatchExport() {
  if (!dateFiltered.value.length) return
  exporting.value = true
  try {
    const ids = dateFiltered.value.map((x) => x.id).join(',')
    const res = await exportBatchApplication(ids)
    const blob = new Blob([res.data], {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    })
    const label = dateMode.value === 'all' ? '全部' : customLabel.value.replace('📅 ', '')
    downloadBlob(blob, `申请表_${label}_${dateFiltered.value.length}份.docx`)
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    exporting.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const params = activeTab.value ? { status: activeTab.value } : {}
    list.value = await getMyApplications(params)
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

function onTabChange() {
  load()
}

onMounted(load)
</script>

<style scoped>
.list-body {
  padding-top: 8px;
}
.date-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 16px 0;
}
.d-chip {
  border: 1px solid #e5e9f2;
  background: #fff;
  color: #4e5566;
  border-radius: 999px;
  padding: 5px 12px;
  font-size: 12px;
  cursor: pointer;
}
.d-chip.active {
  background: #2f6bff;
  border-color: #2f6bff;
  color: #fff;
}
.batch-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 10px 16px 0;
  padding: 8px 12px;
  border-radius: 8px;
  background: #f2f6ff;
}
.batch-info {
  font-size: 13px;
  color: #2f6bff;
  font-weight: 600;
}
</style>
