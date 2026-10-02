import axios from 'axios'
import { showFailToast } from 'vant'
import { useAuthStore } from '../store/auth'
import { getServerBase } from '../utils/server'

// 统一 axios 实例。
// 后端返回格式：{ code, msg, data }，code === 0 表示成功。
// 浏览器模式同源（''）；安卓 App 模式指向用户设置的服务器地址。
const request = axios.create({
  baseURL: getServerBase(),
  timeout: 60000, // 上传大文件时放宽超时
})

// 请求拦截：自动附带登录态；App 模式下动态指向所设服务器
request.interceptors.request.use((config) => {
  config.baseURL = getServerBase()
  const auth = useAuthStore()
  if (auth.token) config.headers.Authorization = `Bearer ${auth.token}`
  return config
})

// 响应拦截：剥掉外层，统一处理业务错误与 HTTP 错误
// config.silent === true 时（后台轮询等场景）不弹错误 toast
request.interceptors.response.use(
  (res) => {
    // 文件下载（blob）：直接放行完整响应，由调用方处理文件流与文件名
    if (res.config.responseType === 'blob') return res
    const body = res.data
    if (body && body.code === 0) return body.data
    // 业务错误（配额不足、参数错误等）
    if (!res.config.silent) showFailToast(body?.msg || '请求失败')
    return Promise.reject(body)
  },
  (err) => {
    const status = err.response?.status
    const msg = err.response?.data?.msg
    if (status === 401) {
      // 登录失效：清除本地态，跳登录页
      const auth = useAuthStore()
      auth.logout()
      window.location.hash = '#/login'
    } else if (!err.config?.silent) {
      if (status === 403) {
        showFailToast(msg || '无权限访问')
      } else {
        showFailToast(msg || '网络异常，请稍后再试')
      }
    }
    return Promise.reject(err)
  },
)

export default request
