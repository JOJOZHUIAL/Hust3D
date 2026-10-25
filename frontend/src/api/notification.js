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

// 按类型已读（进入对应页面时调用），返回剩余未读数 { count }
export const readTypeNotifications = (ntype) => request.post(`/api/notification/read-type/${ntype}`)

// 待确认的取件提醒（首页弹窗用）：{ count, items: [{ id, title, body, application }] }
export const getPickupReminders = (silent = true) =>
  request.get('/api/notification/pickup', { silent })

// 确认取件提醒（首页「我知道了」）：传 ids 只确认指定条目，不传则全部确认
export const ackPickupReminders = (ids) =>
  request.post('/api/notification/pickup/ack', ids && ids.length ? { ids } : {})
