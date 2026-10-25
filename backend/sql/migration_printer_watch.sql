-- =============================================================
-- 迁移：打印机绑定 + 打印进度自动完成
--
-- 新增字段：
--   file_name          STL 原始文件名（打印机状态页「正在打印 xxx.stl」展示用）
--   printer_id         绑定的打印机（printers.id）
--   printer_name       打印机名称快照
--   print_state        最近观察到的打印机状态（RUNNING / PAUSE / FINISH …）
--   print_progress     最近观察到的打印进度 0-100
--   print_seen_running 是否已确认打印机真的开始打印（防误判：避免打印机停在
--                      上一单的 FINISH/100% 时把新申请瞬间判为完成）
--   completed_auto     是否由打印机进度自动标记完成
--
-- 使用方式：mysql -uroot -p < migration_printer_watch.sql
-- 说明：后端启动时 app.py 的 _ensure_columns() 会自动补这些列，
--       正常情况下无需手工执行本脚本（此处仅作留档 / 手工迁移用）。
-- =============================================================
USE hust_3d;

ALTER TABLE print_applications
  ADD COLUMN file_name          VARCHAR(255) NULL COMMENT 'STL 原始文件名（展示用）' AFTER file_url,
  ADD COLUMN printer_id         INT          NULL COMMENT '绑定的打印机 printers.id' AFTER printed_by_student_id,
  ADD COLUMN printer_name       VARCHAR(64)  NULL COMMENT '打印机名称快照' AFTER printer_id,
  ADD COLUMN print_state        VARCHAR(16)  NULL COMMENT '最近观察到的打印机状态 RUNNING/FINISH' AFTER printer_name,
  ADD COLUMN print_progress     INT          NULL COMMENT '最近观察到的打印进度 0-100' AFTER print_state,
  ADD COLUMN print_actual_file  VARCHAR(255) NULL COMMENT '打印机当前上报的真实文件名（可能是别的申请）' AFTER print_progress,
  ADD COLUMN print_matched      TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '打印机当前文件是否就是本申请' AFTER print_actual_file,
  ADD COLUMN print_seen_running TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否已确认打印机真的开始打印' AFTER print_matched,
  ADD COLUMN completed_auto     TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否由打印机进度自动标记完成' AFTER print_seen_running;

-- 存量数据：历史申请的文件名用落盘文件名兜底（仅展示用途）
UPDATE print_applications
   SET file_name = SUBSTRING_INDEX(file_url, '/', -1)
 WHERE file_name IS NULL AND file_url IS NOT NULL;
