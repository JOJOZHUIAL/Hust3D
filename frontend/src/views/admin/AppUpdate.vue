<template>
  <div class="page admin page--wide">
    <van-nav-bar title="应用更新" left-arrow fixed placeholder @click-left="$router.replace('/admin')" />

    <div class="au">
      <!-- 当前线上版本 -->
      <div class="sec-title">当前线上版本</div>
      <div v-if="latest" class="au-card">
        <div class="au-card-head">
          <div class="au-ver-badge">
            <span class="au-ver-name">{{ latest.version_name || "v" + latest.version_code }}</span>
            <span class="au-ver-code">versionCode {{ latest.version_code }}</span>
          </div>
          <van-tag type="success" round>线上生效中</van-tag>
        </div>

        <div class="au-meta">
          <div class="au-meta-item">
            <span class="au-meta-label">安装包</span>
            <span class="au-meta-val">{{ latest.size_text || "—" }}</span>
          </div>
          <div class="au-meta-item">
            <span class="au-meta-label">发布时间</span>
            <span class="au-meta-val">{{ latest.created_at || "—" }}</span>
          </div>
          <div class="au-meta-item">
            <span class="au-meta-label">发布人</span>
            <span class="au-meta-val">{{ latest.publisher || "—" }}</span>
          </div>
        </div>

        <div v-if="latest.note" class="au-note">
          <div class="au-note-label">更新说明</div>
          <div class="au-note-text">{{ latest.note }}</div>
        </div>
      </div>
      <div v-else class="au-card au-card--empty">
        <van-icon name="info-o" size="20" />
        <div>
          <div class="au-empty-title">还没有发布过 APK</div>
          <div class="au-empty-sub">上传后，已安装旧版本的 App 下次启动会提示更新</div>
        </div>
      </div>

      <!-- 上传新版本 -->
      <div class="sec-title">上传新版本</div>
      <van-cell-group inset class="au-form">
        <van-field
          v-model="form.version_code"
          type="digit"
          label="版本号"
          placeholder="整数，需大于线上最新"
          maxlength="9"
          :border="true"
        >
          <template #button>
            <span class="au-field-tip">versionCode</span>
          </template>
        </van-field>
        <van-field v-model="form.version_name" label="版本名称" placeholder="选填，如 1.3" maxlength="32" />
        <van-field
          v-model="form.note"
          type="textarea"
          rows="3"
          autosize
          label="更新说明"
          placeholder="会显示在 App 的更新弹窗里，可换行"
          maxlength="500"
          show-word-limit
        />
        <div class="au-picker" :class="{ 'has-file': !!file }" @click="pickFile">
          <van-icon :name="file ? 'passed' : 'upgrade'" size="22" class="au-picker-icon" />
          <div class="au-picker-body">
            <div class="au-picker-title">{{ file ? file.name : "选择 APK 文件" }}</div>
            <div class="au-picker-sub">
              {{ file ? `${(file.size / 1024 / 1024).toFixed(1)} MB · 点击可重新选择` : "仅支持 .apk，最大 300MB" }}
            </div>
          </div>
        </div>
      </van-cell-group>

      <input
        ref="fileInput"
        type="file"
        accept=".apk,application/vnd.android.package-archive"
        class="hidden-file"
        @change="onFile"
      />

      <div class="au-btns">
        <van-button
          block
          round
          type="primary"
          :loading="uploading"
          :disabled="!file"
          loading-text="上传中，请勿关闭…"
          @click="onUpload"
        >
          上传并发布
        </van-button>
      </div>
      <p class="au-tip">
        版本号需与打包时 build.gradle 的 <b>versionCode</b> 一致（<code>build_apk.py</code>
        会自动递增并打印）；App 端用「已安装的 versionCode ＜ 线上版本号」判断是否需要提示更新。
      </p>

      <!-- 最新版本下载 -->
      <div v-if="latest" class="au-latest">
        <div class="au-latest-info">
          <div class="au-latest-ver">{{ latest.version_name || "v" + latest.version_code }}</div>
          <div class="au-latest-meta">{{ latest.size_text || "—" }} · {{ latest.created_at }}</div>
        </div>
        <van-button
          size="small"
          type="primary"
          round
          icon="down"
          :loading="downloadingId === latest.id"
          @click="onDownload(latest)"
        >
          下载 APK
        </van-button>
      </div>

      <!-- 发布历史 -->
      <div class="sec-title">
        发布历史
        <span v-if="list.length" class="sec-count">{{ list.length }}</span>
      </div>
      <div v-if="list.length" class="au-history">
        <div v-for="(r, idx) in list" :key="r.id" class="au-hitem">
          <div class="au-hitem-main">
            <div class="au-hitem-head">
              <span class="au-hitem-ver">{{ r.version_name || "v" + r.version_code }}</span>
              <van-tag v-if="idx === 0" type="success" round>当前</van-tag>
              <span class="au-hitem-code">#{{ r.version_code }}</span>
            </div>
            <div class="au-hitem-meta">{{ r.created_at }} · {{ r.size_text || "—" }} · {{ r.publisher || "—" }}</div>
            <div v-if="r.note" class="au-hitem-note">{{ r.note }}</div>
          </div>
          <div class="au-hitem-btns">
            <van-button
              size="mini"
              plain
              round
              type="primary"
              :loading="downloadingId === r.id"
              @click="onDownload(r)"
            >
              下载
            </van-button>
            <van-button size="mini" plain round type="danger" @click="onDelete(r)">删除</van-button>
          </div>
        </div>
      </div>
      <van-cell-group v-else inset>
        <van-cell title="暂无发布记录" />
      </van-cell-group>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { showConfirmDialog, showSuccessToast, showFailToast } from 'vant'
import { getAppReleases, uploadAppRelease, deleteAppRelease } from '../../api/app'
import { downloadBlob } from '../../api/application'
import { assetUrl } from '../../utils/server'

const list = ref([])
const latest = computed(() => list.value[0] || null)
const uploading = ref(false)
const file = ref(null)
const fileInput = ref(null)
const form = ref({ version_code: '', version_name: '', note: '' })

async function load() {
  try {
    list.value = (await getAppReleases()) || []
    // 默认给出下一个版本号，省得手填错
    const next = (latest.value?.version_code || 0) + 1
    form.value.version_code = String(next)
    form.value.version_name = `1.${next}`
  } catch (e) {
    /* 拦截器已提示 */
  }
}

// —— APK 下载（blob 方式保证文件名正确） ——
const downloadingId = ref(0)

async function onDownload(r) {
  downloadingId.value = r.id
  try {
    const res = await fetch(assetUrl(r.file_url))
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const blob = await res.blob()
    downloadBlob(blob, r.file_name || `hust3d-v${r.version_code}.apk`)
  } catch (e) {
    showFailToast('下载失败，请稍后重试')
  } finally {
    downloadingId.value = 0
  }
}

function pickFile() {
  fileInput.value?.click()
}

function onFile(e) {
  const f = e.target.files?.[0]
  e.target.value = ''
  if (!f) return
  if (!f.name.toLowerCase().endsWith('.apk')) {
    showFailToast('只支持 .apk 文件')
    return
  }
  file.value = f
}

async function onUpload() {
  const code = String(form.value.version_code || '').trim()
  if (!/^\d+$/.test(code) || Number(code) <= 0) {
    showFailToast('版本号必须是不小于 1 的整数')
    return
  }
  if (!file.value) {
    showFailToast('请选择 APK 文件')
    return
  }
  uploading.value = true
  const fd = new FormData()
  fd.append('file', file.value)
  fd.append('version_code', code)
  fd.append('version_name', form.value.version_name || '')
  fd.append('note', form.value.note || '')
  try {
    await uploadAppRelease(fd)
    showSuccessToast('已发布，App 下次启动会提示更新')
    file.value = null
    form.value.note = ''
    await load()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    uploading.value = false
  }
}

async function onDelete(r) {
  try {
    await showConfirmDialog({
      title: '删除版本',
      message: `确定删除 ${r.version_name || ''} #${r.version_code} 吗？\nAPK 文件也会从服务器删除。`,
    })
  } catch (e) {
    return
  }
  try {
    await deleteAppRelease(r.id)
    showSuccessToast('已删除')
    await load()
  } catch (e) {
    /* 拦截器已提示 */
  }
}

onMounted(load)
</script>

<style scoped>
.au-latest {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 0 16px 14px;
  padding: 14px 16px;
  border-radius: 14px;
  background: #f2f6ff;
}
.au-latest-ver {
  font-size: 15px;
  font-weight: 600;
  color: #1a2233;
}
.au-latest-meta {
  margin-top: 4px;
  font-size: 12px;
  color: #969799;
}
.au-hitem-btns {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-end;
}

.au {
  padding: 4px 0 40px;
}

/* 分组小标题 */
.sec-title {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 18px 20px 8px;
  font-size: 15px;
  font-weight: 600;
  color: #1a2233;
}
.sec-count {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: #eef3ff;
  color: #2f6bff;
  font-size: 11px;
  font-weight: 600;
  line-height: 18px;
  text-align: center;
}

/* 线上版本卡片 */
.au-card {
  margin: 0 16px;
  padding: 16px 16px 14px;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 4px 16px rgba(20, 46, 104, 0.07);
}
.au-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.au-ver-badge {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.au-ver-name {
  font-size: 22px;
  font-weight: 700;
  color: #1a2233;
  line-height: 1.2;
}
.au-ver-code {
  font-size: 12px;
  color: #969799;
}
.au-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 20px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #f0f2f5;
}
.au-meta-item {
  display: flex;
  gap: 6px;
  font-size: 12px;
}
.au-meta-label {
  color: #969799;
}
.au-meta-val {
  color: #323233;
}
.au-note {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #f7f9ff;
}
.au-note-label {
  font-size: 12px;
  color: #969799;
  margin-bottom: 4px;
}
.au-note-text {
  font-size: 13px;
  line-height: 1.7;
  color: #323233;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 空状态卡片 */
.au-card--empty {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #2f6bff;
}
.au-empty-title {
  font-size: 14px;
  font-weight: 600;
  color: #1a2233;
}
.au-empty-sub {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: #969799;
}

/* 表单 */
.au-form {
  overflow: hidden;
}
.au-field-tip {
  font-size: 12px;
  color: #c8c9cc;
}

/* 选文件区 */
.au-picker {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 16px 16px;
  padding: 16px 14px;
  border: 1px dashed #d8dde8;
  border-radius: 12px;
  background: #fafbfe;
  cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease;
}
.au-picker:active {
  background: #f2f6ff;
  border-color: #2f6bff;
}
.au-picker.has-file {
  border-style: solid;
  border-color: #07c160;
  background: #f4fdf8;
}
.au-picker-icon {
  color: #2f6bff;
  flex-shrink: 0;
}
.au-picker.has-file .au-picker-icon {
  color: #07c160;
}
.au-picker-body {
  min-width: 0;
}
.au-picker-title {
  font-size: 14px;
  font-weight: 600;
  color: #1a2233;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.au-picker-sub {
  margin-top: 3px;
  font-size: 12px;
  color: #969799;
}
.hidden-file {
  display: none;
}

.au-btns {
  margin: 16px 16px 0;
}
.au-tip {
  margin: 12px 20px 0;
  font-size: 12px;
  line-height: 1.75;
  color: #969799;
}
.au-tip code {
  padding: 1px 4px;
  border-radius: 4px;
  background: #f2f4f8;
  font-size: 11px;
}

/* 发布历史 */
.au-history {
  margin: 0 16px;
  border-radius: 14px;
  background: #fff;
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(20, 46, 104, 0.06);
}
.au-hitem {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid #f2f4f8;
}
.au-hitem:last-child {
  border-bottom: none;
}
.au-hitem-main {
  flex: 1;
  min-width: 0;
}
.au-hitem-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.au-hitem-ver {
  font-size: 15px;
  font-weight: 600;
  color: #1a2233;
}
.au-hitem-code {
  font-size: 12px;
  color: #c8c9cc;
}
.au-hitem-meta {
  margin-top: 4px;
  font-size: 12px;
  color: #969799;
}
.au-hitem-note {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: #646566;
  white-space: pre-wrap;
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

@media (min-width: 768px) {
  .au-card,
  .au-history {
    margin: 0 36px;
  }
  .sec-title {
    padding: 18px 40px 8px;
  }
  .au-btns {
    margin: 16px 36px 0;
  }
  .au-tip {
    margin: 12px 40px 0;
  }
}
</style>
