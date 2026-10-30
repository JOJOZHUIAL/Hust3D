import request from './request'

// 获取教务系统登录验证码（真实模式返回 base64 图片）
export const getCaptcha = () => request.get('/api/auth/captcha', { timeout: 10000 })

// 登录页公开信息（公共管理员账号名 / 是否 mock 模式）
export const getLoginMode = () => request.get('/api/auth/login-mode', { timeout: 8000 })

// 学号密码登录（对接教务系统 CAS；公共管理员账号走本地校验）
export const casLogin = (data) => request.post('/api/auth/cas-login', data)

// 退出登录
export const logout = () => request.post('/api/auth/logout')
