-- =============================================================
-- 迁移脚本：去微信化，users 表移除 openid，学号变为主身份
--
-- 适用：从「微信 OAuth 版本」升级到「纯网页端」版本的已有数据库。
-- 执行前请先备份。执行方式：
--   mysql -uroot -p < migration_drop_openid.sql
-- =============================================================

USE hust_3d;

-- 清理微信流程可能产生的「只建了 openid、未绑定学号」的脏数据
DELETE FROM users WHERE student_id IS NULL OR student_id = '';

-- 移除 openid 列（其唯一键 uk_openid 一并删除）
ALTER TABLE users DROP COLUMN openid;

-- 学号改为非空（登录即建号，必有学号）
ALTER TABLE users MODIFY student_id VARCHAR(32) NOT NULL COMMENT '学号';
