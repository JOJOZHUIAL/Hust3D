import request from './request'

// 扫码查询：{ exists, item }
export const scanConsumable = (barcode) =>
  request.get('/api/consumable/scan', { params: { barcode } })

// 入库：新条码建档或已有条码累加
export const stockInConsumable = (data) => request.post('/api/consumable/stock-in', data)

// 拆封：库存 -1
export const openConsumable = (data) => request.post('/api/consumable/open', data)

// 进出流水
export const getConsumableLogs = (limit = 100) =>
  request.get('/api/consumable/logs', { params: { limit } })

// 撤回本人的一条流水记录（误操作用），返回恢复后的耗材信息
export const undoConsumableLog = (logId) => request.delete(`/api/consumable/logs/${logId}`)

// 台账列表（keyword: 名称/材质/颜色/条码模糊筛选）
export const getConsumableList = (keyword = '') =>
  request.get('/api/consumable/list', { params: keyword ? { keyword } : {} })

// 编辑耗材信息（条形码不变）
export const updateConsumable = (data) => request.put('/api/consumable/update', data)
