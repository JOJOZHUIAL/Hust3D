<template>
  <div class="sig-pad">
    <canvas ref="canvasRef" class="sig-canvas" :style="{ height: height + 'px' }"></canvas>
    <div class="sig-toolbar">
      <span class="sig-hint">请在框内手写签名</span>
      <van-button size="mini" plain type="primary" @click="clear">清空重写</van-button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import SignaturePad from 'signature_pad'

const props = defineProps({
  height: { type: Number, default: 160 },
})
const emit = defineEmits(['change'])

const canvasRef = ref(null)
let pad = null

function emitChange() {
  emit('change', isEmpty())
}

onMounted(() => {
  const canvas = canvasRef.value
  const cssWidth = canvas.offsetWidth || window.innerWidth - 32
  // 适配高分屏：按 devicePixelRatio 放大画布，保证签名清晰
  const ratio = Math.max(window.devicePixelRatio || 1, 1)
  canvas.width = cssWidth * ratio
  canvas.height = props.height * ratio
  canvas.style.width = '100%'
  const ctx = canvas.getContext('2d')
  ctx.scale(ratio, ratio)

  pad = new SignaturePad(canvas, { penColor: '#1a1a1a', backgroundColor: '#ffffff' })
  pad.addEventListener('endStroke', emitChange)
})

function isEmpty() {
  return pad ? pad.isEmpty() : true
}

function clear() {
  if (pad) pad.clear()
  emitChange()
}

function toDataURL() {
  return pad && !pad.isEmpty() ? pad.toDataURL('image/png') : ''
}

// 暴露给父组件调用
defineExpose({ toDataURL, isEmpty, clear })
</script>

<style scoped>
.sig-pad {
  border: 1px dashed #c8c9cc;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}
.sig-canvas {
  display: block;
  width: 100%;
  touch-action: none;
}
.sig-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-top: 1px solid #ebedf0;
}
.sig-hint {
  font-size: 12px;
  color: #969799;
}
</style>
