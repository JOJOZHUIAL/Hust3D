-- ===============================================================
-- 新电脑 MySQL 初始化脚本（backend\.env 使用的账号授权 + 建库）
--
-- 用法：用 root 登录 MySQL 后整体执行一次。
--   命令行：mysql -uroot -p < mysql_init.sql
--   或在 Navicat / MySQL Workbench 中打开运行。
--
-- ⚠️ 把下面两处 'YourPassword123' 替换成 backend\.env 里 DB_PASSWORD 的值
-- ===============================================================

-- 1. 建库（utf8mb4 支持中文与表情）
CREATE DATABASE IF NOT EXISTS hust_3d DEFAULT CHARACTER SET utf8mb4;

-- 2. 建账号（若已存在则跳过）并统一密码（与 .env 的 DB_PASSWORD 保持完全一致）
CREATE USER IF NOT EXISTS 'hust3d'@'localhost' IDENTIFIED BY 'YourPassword123';
ALTER USER 'hust3d'@'localhost' IDENTIFIED BY 'YourPassword123';

-- 3. 授权（仅 hust_3d 库的全部权限）
GRANT ALL PRIVILEGES ON hust_3d.* TO 'hust3d'@'localhost';
FLUSH PRIVILEGES;

-- 4. 验证（应能列出 hust_3d）
SHOW GRANTS FOR 'hust3d'@'localhost';

-- 表结构无需手动创建：后端启动时会自动补建缺失的表（db.create_all）。
-- 如需查看完整建表脚本（含注释），见 sql/schema.sql。
