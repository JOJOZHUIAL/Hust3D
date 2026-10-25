import request from './request'

// 待审批列表
export const getPendingApplications = () => request.get('/api/admin/applications/pending')

// 全部申请列表（可选状态筛选）
export const getAllApplications = (params) => request.get('/api/admin/applications', { params })

// 审批操作（action: approve / reject，拒绝需带 comment）
export const reviewApplication = (data) => request.post('/api/admin/application/review', data)

// 更新打印状态（printing 时带 printer_id 绑定打印机）
export const updateApplicationStatus = (data) => request.put('/api/admin/application/status', data)

// 批量导出申请表（ZIP，里面每个申请一个 Word）：params = { start, end, status? }
export const exportApplications = (params) =>
  request.get('/api/admin/applications/export', { params, responseType: 'blob' })

// —— 管理员管理（仅超级管理员） ——
export const getAdminList = () => request.get('/api/admin/admins')

export const searchUsers = (keyword) => request.get('/api/admin/users/search', { params: { keyword } })

export const setUserRole = (data) => request.post('/api/admin/set-role', data)

// 反馈审核：approve=通过(+1)；reject=拒绝(可重传)
export const reviewFeedback = (data) => request.post('/api/admin/feedback/review', data)

// —— 取件短信通知（SmsForwarder 等手机网关）——
// 手动（重新）发送取件短信给申请人
export const resendSms = (appId) => request.post(`/api/admin/application/send-sms/${appId}`)

// 短信网关配置（脱敏）
export const getSmsConfig = () => request.get('/api/admin/sms/config')

// 短信网关状态：是否可达 + 待发送条数
export const getSmsStatus = () => request.get('/api/admin/sms/status')

// 监听窗口列表（含每个窗口是否可达）
export const getSmsGateways = () => request.get('/api/admin/sms/gateways')

// 新增 / 删除监听窗口（直接写回 .env，立即生效）
export const addSmsGateway = (url) => request.post('/api/admin/sms/gateways', { url })
export const removeSmsGateway = (url) => request.delete('/api/admin/sms/gateways', { params: { url } })

// 短信记录（含待发送队列）
export const getSmsMessages = (params) => request.get('/api/admin/sms/messages', { params })

// 管理员自定义发短信
export const sendSms = (data) => request.post('/api/admin/sms/send', data)

// 重发某条短信
export const retrySms = (id) => request.post(`/api/admin/sms/messages/${id}/retry`)

// 删除某条短信记录
export const deleteSms = (id) => request.delete(`/api/admin/sms/messages/${id}`)

// 发一条测试短信到指定手机号
export const testSms = (phone) => request.post('/api/admin/sms/test', { phone })
