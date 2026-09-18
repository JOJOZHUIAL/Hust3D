import request from './request'

// 公告列表（最新在前，不含正文）
export const getNoticeList = () => request.get('/api/notice/list')

// 公告详情（含正文）
export const getNoticeDetail = (id) => request.get(`/api/notice/${id}`)

// —— 以下仅管理员 ——
export const createNotice = (data) => request.post('/api/notice/create', data)

export const updateNotice = (data) => request.put('/api/notice/update', data)

export const deleteNotice = (id) => request.delete(`/api/notice/delete/${id}`)
