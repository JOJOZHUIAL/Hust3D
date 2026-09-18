<template>
  <div class="login-page">
    <!-- 登录卡片：校园背景 + 毛玻璃 -->
    <div class="login-card">
      <div class="brand-row">
        <img :src="hustRound" class="school-logo" alt="哈尔滨理工大学" />
        <img :src="clubLogo" class="club-logo" alt="大学生创新创业协会" />
      </div>
      <h1 class="title">3D 打印服务</h1>
      <p class="sub">哈尔滨理工大学 · 大学生创新创业协会</p>

      <van-cell-group inset class="login-form">
        <van-field
          v-model="studentId"
          name="student_id"
          label="学号"
          placeholder="请输入学号"
          clearable
          autocomplete="off"
        />
        <van-field
          v-model="password"
          type="password"
          name="password"
          label="密码"
          placeholder="请输入教务系统密码"
          clearable
          @keyup.enter="onSubmit"
        />
        <van-field
          v-if="captchaRequired"
          v-model="captchaCode"
          name="captcha"
          label="验证码"
          placeholder="请输入验证码"
          maxlength="6"
          clearable
        >
          <template #button>
            <img
              v-if="captchaImg"
              :src="captchaImg"
              class="captcha-img"
              alt="验证码"
              title="点击刷新"
              @click="refreshCaptcha"
            />
            <van-loading v-else size="20" />
          </template>
        </van-field>
      </van-cell-group>

      <div class="login-btn">
        <van-button round block type="primary" :loading="loading" @click="onSubmit">登录</van-button>
      </div>

      <p class="login-tip">登录即使用哈尔滨理工大学教务统一身份认证</p>

      <img :src="hustWide" class="school-wide" alt="Harbin University of Science and Technology" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { showSuccessToast, showFailToast } from 'vant'
import { casLogin, getCaptcha } from '../api/auth'
import { useAuthStore } from '../store/auth'
import clubLogo from '../assets/login/club-logo.jpg'
import hustRound from '../assets/login/hust-round.png'
import hustWide from '../assets/login/hust-wide.png'
import campusImg from '../assets/login/campus.jpg'

document.documentElement.style.setProperty('--login-bg', `url(${campusImg})`)

const router = useRouter()
const auth = useAuthStore()
const studentId = ref('')
const password = ref('')
const loading = ref(false)

// 验证码相关
const captchaRequired = ref(false)
const captchaId = ref('')
const captchaImg = ref('')
const captchaCode = ref('')

onMounted(refreshCaptcha)

async function refreshCaptcha() {
  try {
    const data = await getCaptcha()
    captchaRequired.value = !!data.captcha_required
    if (data.captcha_required) {
      captchaId.value = data.captcha_id
      const mime = data.captcha_type || 'image/png'
      captchaImg.value = 'data:' + mime + ';base64,' + data.captcha_img
      captchaCode.value = ''
    }
  } catch (e) {
    /* 拦截器已提示 */
  }
}

async function onSubmit() {
  if (!studentId.value.trim()) {
    showFailToast('请输入学号')
    return
  }
  if (!password.value) {
    showFailToast('请输入密码')
    return
  }
  if (captchaRequired.value && !captchaCode.value.trim()) {
    showFailToast('请输入验证码')
    return
  }

  loading.value = true
  try {
    const payload = {
      student_id: studentId.value.trim(),
      password: password.value,
    }
    if (captchaRequired.value) {
      payload.captcha_id = captchaId.value
      payload.captcha_code = captchaCode.value.trim()
    }
    const data = await casLogin(payload)
    auth.setToken(data.token)
    auth.setUser(data.user)
    showSuccessToast('登录成功')
    router.replace({ name: 'home' })
  } catch (e) {
    // 错误提示已由 axios 拦截器统一处理；验证码错误时刷新一张新的
    if (captchaRequired.value) refreshCaptcha()
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  background-image:
    linear-gradient(180deg, rgba(16, 38, 84, 0.42), rgba(16, 38, 84, 0.6)),
    var(--login-bg);
  background-size: cover;
  background-position: center;
}

.login-card {
  width: 100%;
  max-width: 400px;
  padding: 26px 20px 20px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.brand-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
}
.club-logo {
  width: 68px;
  height: 68px;
  border-radius: 16px;
  object-fit: cover;
  box-shadow: 0 2px 10px rgba(31, 56, 120, 0.18);
}
.school-logo {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  object-fit: cover;
  background: #fff;
}
.title {
  margin: 14px 0 0;
  text-align: center;
  font-size: 22px;
  color: #16264f;
  letter-spacing: 1px;
}
.sub {
  margin: 6px 0 14px;
  text-align: center;
  font-size: 12px;
  color: #8a93a6;
}
.login-form {
  background: #f7f8fa;
  border-radius: 10px;
  overflow: hidden;
}
.login-btn {
  margin: 18px 16px 0;
}
.login-tip {
  margin: 14px 0 0;
  text-align: center;
  font-size: 12px;
  color: #a6adbc;
}
.school-wide {
  display: block;
  height: 26px;
  margin: 16px auto 0;
  opacity: 0.9;
}
.captcha-img {
  height: 32px;
  width: auto;
  border-radius: 4px;
  cursor: pointer;
  vertical-align: middle;
}

/* 桌面端：背景全屏铺满，卡片居中（覆盖 global.css 的移动端限宽） */
@media (min-width: 768px) {
  .login-page {
    max-width: none;
    margin: 0;
    box-shadow: none;
  }
  .login-card {
    max-width: 420px;
  }
}
</style>
