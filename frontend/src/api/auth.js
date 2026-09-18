import request from './request'

// 获取教务系统登录验证码（真实模式返回 base64 图片）
export const getCaptcha = () => request.get('/api/auth/captcha')

// 学号密码登录（对接教务系统 CAS）
export const casLogin = (data) => request.post('/api/auth/cas-login', data)

// 退出登录
export const logout = () => request.post('/api/auth/logout')
