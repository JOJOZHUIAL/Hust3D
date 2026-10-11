import request from './request'

// 打印机清单（含实时状态摘要）
export const getPrinterList = () => request.get('/api/printer/list')

// 添加打印机 { name, ip, access_code, serial? }
export const addPrinter = (data) => request.post('/api/printer/add', data)

// 删除打印机
export const deletePrinter = (id) => request.delete(`/api/printer/delete/${id}`)

// 单台打印机实时状态（轮询）
export const getPrinterStatus = (id) => request.get(`/api/printer/${id}/status`)
