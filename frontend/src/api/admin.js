import request from './request'

// 待审批列表
export const getPendingApplications = () => request.get('/api/admin/applications/pending')

// 全部申请列表（可选状态筛选）
export const getAllApplications = (params) => request.get('/api/admin/applications', { params })

// 审批操作（action: approve / reject，拒绝需带 comment）
export const reviewApplication = (data) => request.post('/api/admin/application/review', data)

// 更新打印状态（printing / completed / cancelled）
export const updateApplicationStatus = (data) => request.put('/api/admin/application/status', data)
