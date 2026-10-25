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

    <div class="list-body">
      <van-empty v-if="!loading && dateFiltered.length === 0" description="暂无申请记录" />
      <!-- 每条申请一张圆角卡片 -->
      <div v-else class="app-list">
        <van-cell
          v-for="item in dateFiltered"
          :key="item.id"
          class="app-card"
          :title="item.apply_no"
          :label="`${PURPOSE_TEXT[item.purpose] || item.purpose} · ${item.created_at}`"
          is-link
          @click="$router.push(`/application/${item.id}`)"
        >
          <template #value>
            <van-tag round :color="STATUS[item.status]?.color">{{ STATUS[item.status]?.text }}</van-tag>
            <van-tag round v-if="item.feedback_url && item.feedback_reviewed === false" color="#ffd21e">反馈审核中</van-tag>
            <van-tag round v-else-if="item.feedback_url && item.feedback_reviewed !== 2" color="#07c160">已反馈</van-tag>
            <van-tag round v-else-if="item.expired" color="#969799">已过期</van-tag>
            <van-tag round v-else-if="item.status === 'completed'" color="#ff976a">未反馈</van-tag>
          </template>
          <template #right-icon>
            <!-- 待审批且未进入审批流程：可撤回（彻底删除并返还打印次数） -->
            <van-button
              v-if="item.can_withdraw"
              size="mini"
              plain
              round
              type="danger"
              style="margin-right: 6px"
              @click.stop="onWithdraw(item)"
            >
              撤回
            </van-button>
            <!-- 自定义 right-icon 会覆盖默认箭头，这里补回来保持列表观感一致 -->
            <van-icon name="arrow" class="van-cell__right-icon" />
          </template>
        </van-cell>
      </div>
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
import { showConfirmDialog, showSuccessToast } from 'vant'
import { getMyApplications, withdrawApplication } from '../api/application'
import TabBar from '../components/TabBar.vue'
import { STATUS, PURPOSE_TEXT } from '../utils/constants'

const TABS = [
  { value: '', label: '全部' },
  { value: 'pending', label: '待审批' },
  { value: 'approved', label: '已通过' },
  { value: 'printing', label: '打印中' },
  { value: 'completed', label: '已完成' },
  { value: 'expired', label: '已过期' },
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

// —— 批量导出 Word 已移到管理员「审批管理」右上角（按时间范围导出）——

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

// 撤回申请：等价于删除（记录 + STL/签名文件），并返还 1 次打印机会
async function onWithdraw(item) {
  try {
    await showConfirmDialog({
      title: '撤回申请',
      message: `确定撤回申请 ${item.apply_no} 吗？\n撤回后记录与模型文件将被永久删除，且不消耗打印次数。`,
    })
  } catch (e) {
    return // 取消
  }
  try {
    await withdrawApplication(item.id)
    showSuccessToast('已撤回，打印次数已返还')
    load()
  } catch (e) {
    /* 拦截器已提示 */
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

/* 申请列表：每条一张圆角卡片 */
.app-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px 16px 12px;
}
.app-card {
  border-radius: 14px;
  background: #fff;
  overflow: hidden;
  box-shadow: 0 4px 14px rgba(20, 46, 104, 0.06);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.app-card:active {
  transform: scale(0.99);
  box-shadow: 0 2px 8px rgba(20, 46, 104, 0.1);
}
/* 卡片自带圆角，去掉 cell 默认的分割线 */
.app-card::after {
  display: none;
}
.app-card :deep(.van-cell__title) {
  font-weight: 600;
  color: #1a2233;
}
.app-card :deep(.van-cell__label) {
  margin-top: 4px;
  color: #969799;
}
/* 右侧状态标签：圆润药丸样式，两枚标签之间留一点间距 */
.app-card :deep(.van-cell__value) {
  text-align: right;
}
.app-card :deep(.van-tag) {
  margin-left: 6px;
  padding: 3px 12px;
  font-size: 13px;
  line-height: 18px;
  font-weight: 500;
  border-radius: 999px;
}

@media (min-width: 768px) {
  .app-list {
    padding: 6px 36px 16px;
  }
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
</style>
