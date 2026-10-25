-- =============================================================
-- 迁移：为 print_applications 增加「审批人 / 打印操作人 / 过期」字段
--
-- 新增字段：
--   reviewer_id / reviewer_name / reviewer_student_id        审批人留痕（id + 姓名/学号快照）
--   printed_by_id / printed_by_name / printed_by_student_id  打印操作人留痕
--   completed_at                                             打印完成时间（反馈 7 天计时起点）
--   expired_at                                               反馈超时过期时间
--
-- 使用方式：mysql -uroot -p < migration_approval_info.sql
-- 说明：后端启动时 app.py 的 _ensure_columns() 会自动补这些列，
--       正常情况下无需手工执行本脚本（此处仅作留档 / 手工迁移用）。
-- 幂等：ADD COLUMN IF NOT EXISTS 需 MySQL 8.0.29+，低版本请先确认列不存在。
-- =============================================================
USE hust_3d;

ALTER TABLE print_applications
  ADD COLUMN reviewer_id          INT          NULL COMMENT '审批人 users.id' AFTER reviewed_at,
  ADD COLUMN reviewer_name        VARCHAR(64)  NULL COMMENT '审批人姓名快照' AFTER reviewer_id,
  ADD COLUMN reviewer_student_id  VARCHAR(32)  NULL COMMENT '审批人学号快照' AFTER reviewer_name,
  ADD COLUMN printed_by_id        INT          NULL COMMENT '打印操作人 users.id' AFTER printed_at,
  ADD COLUMN printed_by_name      VARCHAR(64)  NULL COMMENT '打印操作人姓名快照' AFTER printed_by_id,
  ADD COLUMN printed_by_student_id VARCHAR(32) NULL COMMENT '打印操作人学号快照' AFTER printed_by_name,
  ADD COLUMN completed_at         DATETIME     NULL COMMENT '打印完成时间（反馈计时起点）' AFTER printed_by_student_id,
  ADD COLUMN expired_at           DATETIME     NULL COMMENT '反馈超时过期时间' AFTER completed_at;

-- 存量数据回填：已完成的申请没有 completed_at，用开始打印时间兜底（避免一升级就全部过期）
UPDATE print_applications
   SET completed_at = COALESCE(printed_at, updated_at)
 WHERE status = 'completed' AND completed_at IS NULL;
