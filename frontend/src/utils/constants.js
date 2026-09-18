// 状态 -> 展示文案与标签颜色（颜色用 Vant Tag 的 color 值）
export const STATUS = {
  pending: { text: '待审批', color: '#ff976a' },
  approved: { text: '已通过', color: '#07c160' },
  rejected: { text: '已拒绝', color: '#ee0a24' },
  printing: { text: '打印中', color: '#1989fa' },
  completed: { text: '已完成', color: '#7232dd' },
  cancelled: { text: '已取消', color: '#969799' },
}

// 打印用途选项（与后端 ALLOWED_PURPOSE 一致）
export const PURPOSE = [
  { value: 'course', label: '课程作业' },
  { value: 'research', label: '科研项目' },
  { value: 'competition', label: '学科竞赛' },
  { value: 'graduation', label: '毕业设计' },
  { value: 'club', label: '学生社团项目' },
  { value: 'other', label: '其他（请简要说明）' },
]

export const PURPOSE_TEXT = PURPOSE.reduce((m, p) => {
  m[p.value] = p.label
  return m
}, {})

// 服务声明条款（共 5 项，需逐条勾选确认）
export const TERMS = [
  '本人确认所提交模型文件为原创或已获合法授权，不侵犯他人知识产权。',
  '已知悉 3D 打印存在一定误差与失败风险，成品以实际打印效果为准。',
  '承诺在工作室通知后按时领取成品，逾期未领取工作室有权自行处理。',
  '同意工作室对打印过程进行必要记录与统计，仅用于服务改进。',
  '已知晓本学期打印配额规则，并保证所填信息真实、有效。',
]
