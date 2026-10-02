// App 模式服务器地址管理：安卓 App 内页面由本机（https://localhost）加载，
// API 与上传资源需指向电脑上的后端；浏览器模式下保持同源（空串）。
export const SERVER_KEY = 'hust3d_server'

// Capacitor 原生环境（安卓 App）识别
export function isNative() {
  return typeof window !== 'undefined' && !!window.Capacitor?.isNativePlatform?.()
}

export function getServerBase() {
  if (!isNative()) return ''
  return (localStorage.getItem(SERVER_KEY) || '').replace(/\/+$/, '')
}

export function setServerBase(url) {
  if (url) localStorage.setItem(SERVER_KEY, url.trim().replace(/\/+$/, ''))
  else localStorage.removeItem(SERVER_KEY)
}

// 相对资源路径（uploads/...）→ 服务器绝对地址
export function assetUrl(path) {
  if (!path) return ''
  if (path.startsWith('http')) return path
  return getServerBase() + '/' + path
}
