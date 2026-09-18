import request from './request'

// 发送消息（multipart/form-data：content_type + content/file/duration，管理员带 user_id）
export const sendChatMessage = (formData) =>
  request.post('/api/chat/send', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })

// 拉取会话历史（最新 200 条；管理员需带 user_id），返回 { peer, messages }
// silent: 后台轮询时传 true，失败不弹 toast
export const getChatMessages = (params, silent = false) =>
  request.get('/api/chat/messages', { params, silent })

// 管理员：会话列表（每个学生最近一条 + 未读数）
export const getChatConversations = (silent = false) =>
  request.get('/api/chat/conversations', { silent })

// 管理员：可发起会话的联系人名单（全部非管理员用户）
export const getChatContacts = () => request.get('/api/chat/contacts')

// 未读消息数 { count }
export const getChatUnread = (silent = false) => request.get('/api/chat/unread', { silent })
