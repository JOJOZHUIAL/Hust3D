import request from './request'

// 通知列表（最新在前，50 条）
export const getNotificationList = (silent = false) =>
  request.get('/api/notification/list', { silent })

// 未读数 { count }
export const getNotificationUnread = (silent = false) =>
  request.get('/api/notification/unread-count', { silent })

// 单条已读
export const readNotification = (id) => request.post(`/api/notification/read/${id}`)

// 全部已读
export const readAllNotifications = () => request.post('/api/notification/read-all')
