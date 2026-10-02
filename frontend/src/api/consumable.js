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

// 台账列表
export const getConsumableList = () => request.get('/api/consumable/list')
