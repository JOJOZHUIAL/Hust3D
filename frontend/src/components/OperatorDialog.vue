<template>
  <van-dialog
    :show="operatorVisible"
    :title="operatorTitle"
    show-cancel-button
    :before-close="onBeforeClose"
    confirm-button-text="确定"
    cancel-button-text="取消"
    @cancel="cancelOperator"
  >
    <div class="op-box">
      <div class="op-hint">
        {{ operatorHint || '当前是公共管理员账号，请填写实际操作人的学号，系统会把这次操作记在本人名下。' }}
      </div>
      <van-field
        v-model="studentId"
        type="digit"
        maxlength="20"
        label="操作人学号"
        placeholder="例如 2504060306"
        clearable
        autofocus
        @keyup.enter="confirm"
      />
      <div class="op-tip">学号必须是系统里已存在的账号（登录过一次即可）。</div>
    </div>
  </van-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { showFailToast } from 'vant'
import {
  operatorVisible,
  operatorTitle,
  operatorHint,
  submitOperator,
  cancelOperator,
} from '../utils/operator'

const studentId = ref('')

function confirm() {
  const v = studentId.value.trim()
  if (!v) {
    showFailToast('请填写操作人学号')
    return false
  }
  submitOperator(v)
  studentId.value = ''
  return true
}

// 点「确定」时校验；返回 false 阻止关闭
function onBeforeClose(action) {
  if (action !== 'confirm') return true
  return confirm()
}
</script>

<style scoped>
.op-box {
  padding: 8px 0 4px;
}
.op-hint {
  margin: 0 16px 10px;
  font-size: 13px;
  color: #646566;
  line-height: 1.6;
}
.op-tip {
  margin: 8px 16px 12px;
  font-size: 12px;
  color: #969799;
}
</style>
