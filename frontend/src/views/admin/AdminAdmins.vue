<template>
  <div class="page admin page--wide">
    <van-nav-bar title="管理员管理" left-arrow fixed placeholder @click-left="$router.replace('/admin')" />

    <!-- 现任管理员 -->
    <div class="sec-title">现任管理员</div>
    <van-cell-group inset>
      <van-cell v-for="u in admins" :key="u.id">
        <template #icon>
          <div class="u-avatar" :class="{ super: u.role === 'superadmin' }">{{ (u.name || u.student_id || '?')[0] }}</div>
        </template>
        <template #title>
          {{ u.name || u.student_id }}
          <van-tag v-if="u.role === 'superadmin'" color="#7232dd" style="margin-left: 6px">超级管理员</van-tag>
        </template>
        <template #label>{{ u.student_id }} · {{ u.college || '—' }}</template>
        <template #value>
          <van-button
            v-if="u.role === 'admin'"
            size="small"
            plain
            type="danger"
            @click="onDemote(u)"
          >
            移除
          </van-button>
        </template>
      </van-cell>
      <van-empty v-if="!loading && admins.length === 0" description="暂无管理员" />
    </van-cell-group>

    <!-- 添加管理员 -->
    <div class="sec-title">添加管理员</div>
    <van-cell-group inset>
      <van-field
        v-model="keyword"
        label="学号/姓名"
        placeholder="搜索已登录过本系统的用户"
        clearable
        @update:model-value="onSearch"
      />
    </van-cell-group>
    <div v-if="hits.length" class="hit-list">
      <van-cell-group inset>
        <van-cell v-for="u in hits" :key="u.id" :title="u.name || u.student_id" :label="`${u.student_id} · ${u.college || '—'}`">
          <template #value>
            <van-button size="small" type="primary" @click="onPromote(u)">设为管理员</van-button>
          </template>
        </van-cell>
      </van-cell-group>
    </div>
    <p class="hint">
      只有登录过本系统的学号才能被设为管理员；超级管理员由服务器配置文件指定，不可在此修改。
    </p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { showConfirmDialog, showSuccessToast } from 'vant'
import { getAdminList, searchUsers, setUserRole } from '../../api/admin'

const admins = ref([])
const hits = ref([])
const keyword = ref('')
const loading = ref(true)
let searchTimer = null

async function load() {
  loading.value = true
  try {
    admins.value = await getAdminList()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

function onSearch(v) {
  clearTimeout(searchTimer)
  const kw = (v || '').trim()
  if (!kw) {
    hits.value = []
    return
  }
  searchTimer = setTimeout(async () => {
    try {
      hits.value = await searchUsers(kw)
    } catch (e) {
      hits.value = []
    }
  }, 300)
}

async function onPromote(u) {
  try {
    await setUserRole({ student_id: u.student_id, role: 'admin' })
    showSuccessToast(`已将 ${u.name || u.student_id} 设为管理员`)
    hits.value = []
    keyword.value = ''
    load()
  } catch (e) {
    /* 拦截器已提示 */
  }
}

async function onDemote(u) {
  try {
    await showConfirmDialog({
      title: '移除管理员',
      message: `确定移除 ${u.name || u.student_id} 的管理员权限吗？`,
    })
  } catch (e) {
    return
  }
  try {
    await setUserRole({ student_id: u.student_id, role: 'user' })
    showSuccessToast('已移除')
    load()
  } catch (e) {
    /* 拦截器已提示 */
  }
}

onMounted(load)
</script>

<style scoped>
.sec-title {
  padding: 14px 20px 8px;
  font-size: 15px;
  font-weight: 600;
  color: #1a2233;
}
.u-avatar {
  width: 38px;
  height: 38px;
  margin-right: 10px;
  border-radius: 50%;
  background: #dbe4ff;
  color: #2f6bff;
  font-weight: 600;
  display: grid;
  place-items: center;
}
.u-avatar.super {
  background: #ede2ff;
  color: #7232dd;
}
.hit-list {
  margin-top: 10px;
}
.hint {
  margin: 14px 20px 0;
  font-size: 12px;
  line-height: 1.7;
  color: #969799;
}
</style>
