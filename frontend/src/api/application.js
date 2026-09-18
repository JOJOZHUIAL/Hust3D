import request from './request'

// 提交打印申请（multipart/form-data，含 STL 文件与签名）
export const submitApplication = (formData) =>
  request.post('/api/application/submit', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })

// 获取我的申请列表，可选状态筛选
export const getMyApplications = (params) => request.get('/api/application/list', { params })

// 获取申请详情
export const getApplicationDetail = (id) => request.get(`/api/application/detail/${id}`)

// 导出申请为 Word 文档（官方申请表格式），返回完整 axios 响应（blob）
export const exportApplicationForm = (id) =>
  request.get(`/api/application/export/${id}`, { responseType: 'blob' })

// 触发浏览器下载 blob 文件
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

// 打印完成后提交反馈（上传实物图/现场照片，成功后奖励 1 次打印机会）
export const submitFeedback = (id, formData) =>
  request.post(`/api/application/feedback/${id}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
