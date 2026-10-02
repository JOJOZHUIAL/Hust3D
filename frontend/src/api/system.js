import request from './request'

// 本机局域网信息（IP / 端口 / HTTPS 是否启用），供生成手机访问二维码
export const getLanInfo = () => request.get('/api/lan')
