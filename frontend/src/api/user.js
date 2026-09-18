import request from './request'

// 获取当前用户信息
export const getUserInfo = () => request.get('/api/user/info')

// 获取剩余打印次数
export const getQuota = () => request.get('/api/user/quota')
