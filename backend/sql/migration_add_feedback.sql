-- =============================================================
-- 迁移：为 print_applications 增加反馈字段（打印完成后上传实物图/现场照片）
-- 使用方式：mysql -uroot -p < migration_add_feedback.sql
-- 幂等：使用 IF NOT EXISTS 风格（MySQL 8.0 支持 ADD COLUMN IF NOT EXISTS 需 8.0.29+），
--       低版本请手工确认列不存在后再执行。
-- =============================================================
USE hust_3d;

ALTER TABLE print_applications
  ADD COLUMN feedback_url VARCHAR(255) NULL COMMENT '反馈图片路径（实物图/现场照片）' AFTER reviewer_sign,
  ADD COLUMN feedback_at  DATETIME     NULL COMMENT '反馈时间' AFTER feedback_url;
