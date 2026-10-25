import request from './request'

// 最新 App 版本（客户端启动时检查更新用，登录即可）
export const getLatestAppRelease = (silent = true) =>
  request.get('/api/app/latest', { silent })

// —— 以下仅管理员：APK 发布管理 ——
export const getAppReleases = () => request.get('/api/app/releases')

// 上传新版本：FormData（file / version_code / version_name / note）
export const uploadAppRelease = (formData) =>
  request.post('/api/app/releases', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000, // APK 可能几十 MB，放宽超时
  })

export const deleteAppRelease = (id) => request.delete(`/api/app/releases/${id}`)
