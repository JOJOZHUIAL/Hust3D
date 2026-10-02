<template>
  <div class="page admin page--wide">
    <van-nav-bar title="通知管理" left-arrow fixed placeholder @click-left="$router.replace('/admin')">
      <template #right>
        <van-icon name="plus" size="20" @click="openEditor()" />
      </template>
    </van-nav-bar>

    <div class="notice-body">
      <van-empty v-if="!loading && list.length === 0" description="暂无公告，点右上角 + 发布" />
      <van-cell-group inset>
        <van-cell v-for="n in list" :key="n.id" :title="n.title" :label="`${n.publisher} · ${n.created_at}`">
          <template #value>
            <div class="ops">
              <van-button size="small" plain type="primary" @click="openEditor(n)">编辑</van-button>
              <van-button size="small" plain type="danger" @click="onDelete(n)">删除</van-button>
            </div>
          </template>
        </van-cell>
      </van-cell-group>
    </div>

    <!-- 新建/编辑弹层 -->
    <van-popup v-model:show="editorShow" position="bottom" round :style="{ height: '88%' }">
      <div class="editor">
        <div class="editor-title">{{ form.id ? "编辑公告" : "发布新公告" }}</div>
        <van-field
          v-model="form.title"
          label="标题"
          placeholder="请输入标题（≤100字）"
          maxlength="100"
        />
        <van-field
          v-model="form.content"
          label="正文"
          type="textarea"
          rows="10"
          autosize
          maxlength="10000"
          show-word-limit
          placeholder="请输入正文（支持换行）"
        />
        <div class="editor-btns">
          <van-button block round plain @click="editorShow = false">取消</van-button>
          <van-button block round type="primary" :loading="saving" @click="onSave">保存</van-button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { showConfirmDialog, showSuccessToast, showFailToast } from 'vant'
import { getNoticeList, getNoticeDetail, createNotice, updateNotice, deleteNotice } from '../../api/notice'

const list = ref([])
const loading = ref(true)
const saving = ref(false)
const editorShow = ref(false)
const form = ref({ id: null, title: '', content: '' })

async function load() {
  loading.value = true
  try {
    list.value = await getNoticeList()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

function openEditor(row = null) {
  form.value = row
    ? { id: row.id, title: row.title, content: '' } // 正文随后从详情接口补齐
    : { id: null, title: '', content: '' }
  if (row) fillContent(row.id)
  editorShow.value = true
}

async function fillContent(id) {
  try {
    const d = await getNoticeDetail(id)
    form.value.content = d.content || ''
  } catch (e) {
    /* 拦截器已提示 */
  }
}

async function onSave() {
  const title = form.value.title.trim()
  const content = form.value.content.trim()
  if (!title) {
    showFailToast('请填写标题')
    return
  }
  if (!content) {
    showFailToast('请填写正文')
    return
  }
  saving.value = true
  try {
    if (form.value.id) {
      await updateNotice({ id: form.value.id, title, content })
      showSuccessToast('保存成功')
    } else {
      await createNotice({ title, content })
      showSuccessToast('发布成功')
    }
    editorShow.value = false
    load()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    saving.value = false
  }
}

async function onDelete(row) {
  try {
    await showConfirmDialog({
      title: '删除公告',
      message: `确定删除「${row.title}」吗？删除后不可恢复。`,
    })
  } catch (e) {
    return // 取消
  }
  try {
    await deleteNotice(row.id)
    showSuccessToast('已删除')
    load()
  } catch (e) {
    /* 拦截器已提示 */
  }
}

onMounted(load)
</script>

<style scoped>
.notice-body {
  padding-top: 8px;
}
.notice-body :deep(.van-cell__title) {
  white-space: normal;
}
.ops {
  display: flex;
  gap: 8px;
  align-items: center;
}
.editor {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 16px;
  gap: 12px;
  overflow-y: auto;
}
.editor-title {
  text-align: center;
  font-size: 16px;
  font-weight: 600;
  color: #1a2233;
}
.editor-btns {
  display: flex;
  gap: 12px;
  padding: 4px 8px 10px;
}
</style>
