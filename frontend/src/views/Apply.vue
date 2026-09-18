<template>
  <div class="page apply">
    <van-nav-bar title="打印申请" left-arrow fixed placeholder @click-left="$router.back()" />

    <!-- 第一部分：申请人基本信息（系统自动填充） -->
    <div class="form-section">
      <div class="form-section-title">申请人基本信息</div>
      <van-cell-group inset>
        <van-field :model-value="user?.name || ''" label="姓名" readonly />
        <van-field :model-value="user?.college || ''" label="学院" readonly />
        <van-field :model-value="user?.student_id || ''" label="学号" readonly />
        <van-field v-model="phone" label="联系方式" placeholder="请输入手机号" type="tel" maxlength="11" required />
        <van-field v-model="email" label="电子邮箱" placeholder="请输入邮箱" required />
      </van-cell-group>
    </div>

    <!-- 第二部分：打印需求详情 -->
    <div class="form-section">
      <div class="form-section-title">打印需求详情</div>
      <van-cell-group inset>
        <van-cell title="打印用途" :value="purposeText" is-link required @click="showPurpose = true" />
        <van-field
          v-if="purpose === 'other'"
          v-model="purposeOther"
          label="用途说明"
          placeholder="请简要说明打印用途"
          maxlength="100"
        />
        <van-cell title="期望材料" value="PLA（FDM）" />
        <van-cell title="模型数量" center>
          <template #right-icon>
            <van-stepper v-model="modelCount" min="1" max="10" />
          </template>
        </van-cell>
      </van-cell-group>
    </div>

    <!-- 第三部分：模型文件与特别说明 -->
    <div class="form-section">
      <div class="form-section-title">模型文件与特别说明</div>
      <van-cell-group inset>
        <div class="upload-cell">
          <div class="upload-label">STL 模型文件<span class="req">*</span></div>
          <div class="file-upload" @click="pickFile">
            <input ref="fileInput" type="file" accept=".stl" style="display: none" @change="onFileChange" />
            <van-icon :name="rawFile ? 'description' : 'plus'" size="20" />
            <span class="file-name">{{ rawFile ? rawFile.name : '点击选择 .stl 文件（≤50MB）' }}</span>
            <van-icon v-if="rawFile" name="clear" class="file-clear" @click.stop="removeFile" />
          </div>
        </div>
        <van-field
          v-model="remark"
          label="特别说明"
          type="textarea"
          rows="2"
          autosize
          maxlength="500"
          show-word-limit
          placeholder="选填"
        />
      </van-cell-group>
    </div>

    <!-- 第四部分：服务声明与确认 -->
    <div class="form-section">
      <div class="form-section-title">服务声明与确认<span class="req">*</span></div>
      <van-cell-group inset>
        <van-checkbox-group v-model="agreements">
          <van-cell
            v-for="(t, i) in TERMS"
            :key="i"
            clickable
            @click="toggleTerm(i)"
          >
            <template #title>
              <span class="term-text">{{ i + 1 }}. {{ t }}</span>
            </template>
            <template #right-icon>
              <van-checkbox :name="i" ref="termBoxes" @click.stop />
            </template>
          </van-cell>
        </van-checkbox-group>
      </van-cell-group>

      <div class="sign-area">
        <div class="form-section-title">申请人电子签名<span class="req">*</span></div>
        <SignaturePad ref="signRef" :height="160" @change="signEmpty = $event" />
      </div>
    </div>

    <div class="submit-bar">
      <van-button round block type="primary" :loading="submitting" @click="onSubmit">提交申请</van-button>
    </div>

    <!-- 打印用途选择弹层 -->
    <van-popup v-model:show="showPurpose" position="bottom" round>
      <van-picker
        :columns="PURPOSE"
        :columns-field-names="{ text: 'label', value: 'value' }"
        title="选择打印用途"
        @confirm="onPurposeConfirm"
        @cancel="showPurpose = false"
      />
    </van-popup>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { showFailToast, showSuccessToast } from 'vant'
import SignaturePad from '../components/SignaturePad.vue'
import { submitApplication } from '../api/application'
import { useAuthStore } from '../store/auth'
import { PURPOSE, PURPOSE_TEXT, TERMS } from '../utils/constants'

const router = useRouter()
const auth = useAuthStore()
const user = computed(() => auth.user)

const phone = ref(user.value?.phone || '')
const email = ref(user.value?.email || '')

const purpose = ref('')
const showPurpose = ref(false)
const purposeOther = ref('')
const modelCount = ref(1)
const purposeText = computed(() => (purpose.value ? PURPOSE_TEXT[purpose.value] : '请选择'))

const rawFile = ref(null)
const fileInput = ref(null)
const remark = ref('')

const agreements = ref([])
const termBoxes = ref([])
const signRef = ref(null)
const signEmpty = ref(true)

const submitting = ref(false)

function onPurposeConfirm({ selectedValues }) {
  purpose.value = selectedValues[0]
  showPurpose.value = false
}

function toggleTerm(i) {
  if (termBoxes.value[i]) termBoxes.value[i].toggle()
}

function pickFile() {
  fileInput.value?.click()
}

function onFileChange(e) {
  const f = e.target.files[0]
  if (!f) return
  if (!f.name.toLowerCase().endsWith('.stl')) {
    showFailToast('仅支持 .stl 格式文件')
    return
  }
  if (f.size > 50 * 1024 * 1024) {
    showFailToast('文件不能超过 50MB')
    return
  }
  rawFile.value = f
  // 允许重复选择同一文件时也能触发 change
  e.target.value = ''
}

function removeFile() {
  rawFile.value = null
  if (fileInput.value) fileInput.value.value = ''
}

async function onSubmit() {
  const phoneVal = phone.value.trim()
  if (!phoneVal) {
    showFailToast('请填写联系方式')
    return
  }
  if (!/^1\d{10}$/.test(phoneVal)) {
    showFailToast('请填写正确的 11 位手机号')
    return
  }
  const emailVal = email.value.trim()
  if (!emailVal) {
    showFailToast('请填写电子邮箱')
    return
  }
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(emailVal)) {
    showFailToast('请填写正确的电子邮箱')
    return
  }
  if (!purpose.value) {
    showFailToast('请选择打印用途')
    return
  }
  if (purpose.value === 'other' && !purposeOther.value.trim()) {
    showFailToast('请填写打印用途说明')
    return
  }
  if (!rawFile.value) {
    showFailToast('请上传 .stl 模型文件')
    return
  }
  if (agreements.value.length < TERMS.length) {
    showFailToast('请勾选全部服务条款')
    return
  }
  if (signEmpty.value) {
    showFailToast('请手写签名')
    return
  }

  const fd = new FormData()
  fd.append('purpose', purpose.value)
  if (purpose.value === 'other') fd.append('purpose_other', purposeOther.value.trim())
  fd.append('material', 'PLA')
  fd.append('model_count', String(modelCount.value))
  if (remark.value.trim()) fd.append('remark', remark.value.trim())
  fd.append('phone', phoneVal)
  fd.append('email', emailVal)
  fd.append('file', rawFile.value)
  fd.append('sign', signRef.value.toDataURL())

  submitting.value = true
  try {
    const res = await submitApplication(fd)
    showSuccessToast('提交成功')
    router.replace({ name: 'application-detail', params: { id: res.id } })
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.apply {
  padding-bottom: 100px;
}
.upload-cell {
  padding: 12px 16px;
  border-bottom: 1px solid #ebedf0;
}
.upload-label {
  margin-bottom: 8px;
  font-size: 14px;
  color: #323233;
}
.req {
  color: #ee0a24;
}
.file-upload {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  border: 1px dashed #c8c9cc;
  border-radius: 8px;
  color: #969799;
}
.file-name {
  flex: 1;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-clear {
  color: #c8c9cc;
}
.term-text {
  font-size: 13px;
  color: #323233;
  white-space: normal;
}
.sign-area {
  margin-top: 12px;
  padding: 0 16px;
}
.submit-bar {
  margin: 24px 16px 0;
}
</style>
