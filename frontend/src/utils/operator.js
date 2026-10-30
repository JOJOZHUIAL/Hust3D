// 公共管理员（共享账号）操作时，需要登记「实际操作人学号」。
// 用法：
//   const op = await withOperator(auth)
//   if (!op.ok) return
//   payload.operator_student_id = op.studentId   // 普通管理员时为 null
import { ref } from 'vue'

export const operatorVisible = ref(false)
export const operatorTitle = ref('记录操作人')
export const operatorHint = ref('')

let _resolve = null

export function askOperator(title = '记录操作人', hint = '') {
  operatorTitle.value = title
  operatorHint.value = hint
  operatorVisible.value = true
  return new Promise((resolve) => {
    _resolve = resolve
  })
}

export function submitOperator(studentId) {
  operatorVisible.value = false
  const r = _resolve
  _resolve = null
  r && r((studentId || '').trim() || null)
}

export function cancelOperator() {
  operatorVisible.value = false
  const r = _resolve
  _resolve = null
  r && r(null)
}

/**
 * 需要登记操作人的动作前调用：
 *  - 普通管理员 / 超管 → 直接通过（studentId = null）
 *  - 公共管理员 → 弹窗输入学号；取消返回 { ok: false }
 */
export async function withOperator(auth, title, hint) {
  if (!auth?.user?.is_shared_admin) return { ok: true, studentId: null }
  const sid = await askOperator(title, hint)
  if (!sid) return { ok: false }
  return { ok: true, studentId: sid }
}
