-- =============================================================
-- 3D 打印服务管理系统 · 建表脚本（MySQL 8.0）
-- 字符集统一 utf8mb4
--
-- 使用方式：mysql -uroot -p < schema.sql
-- 与 backend/models.py 字段一一对应，请同步维护。
-- =============================================================

CREATE DATABASE IF NOT EXISTS hust_3d
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE hust_3d;

-- ---------------------------------------------------------------
-- 1. 用户表 users
--    学号为身份主键，教务系统登录后自动建号，姓名/学院等随后填充。
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
  id              INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
  student_id      VARCHAR(32)  NOT NULL COMMENT '学号',
  name            VARCHAR(64)  NULL COMMENT '姓名',
  college         VARCHAR(128) NULL COMMENT '学院',
  phone           VARCHAR(32)  NULL COMMENT '联系方式',
  email           VARCHAR(128) NULL COMMENT '邮箱',
  role            VARCHAR(16)  NOT NULL DEFAULT 'user' COMMENT '角色 admin/user',
  semester        VARCHAR(32)  NULL COMMENT '当前学期，如 2026-1',
  remaining_quota INT          NOT NULL DEFAULT 2 COMMENT '本学期剩余打印次数',
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_student_id (student_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- ---------------------------------------------------------------
-- 2. 打印申请表 print_applications
--    对应 Word 表单「附件1 3D打印服务申请表单」。
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS print_applications (
  id             INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
  user_id        INT          NOT NULL COMMENT '申请人',
  apply_no       VARCHAR(32)  NOT NULL COMMENT '申请编号，如 HUST3D20260908001',
  purpose        VARCHAR(32)  NOT NULL COMMENT '用途 course/research/competition/graduation/club/other',
  purpose_other  VARCHAR(255) NULL COMMENT '其他用途说明',
  material       VARCHAR(32)  NOT NULL DEFAULT 'PLA' COMMENT '期望材料',
  model_count    INT          NOT NULL DEFAULT 1 COMMENT '模型数量',
  file_url       VARCHAR(255) NULL COMMENT 'STL 文件相对路径',
  remark         TEXT         NULL COMMENT '特别说明',
  status         VARCHAR(16)  NOT NULL DEFAULT 'pending' COMMENT 'pending/approved/rejected/printing/completed/cancelled',
  admin_comment  TEXT         NULL COMMENT '审批意见/拒绝原因',
  reviewed_at    DATETIME     NULL COMMENT '审批时间',
  printed_at     DATETIME     NULL COMMENT '开始打印时间',
  picked_up      TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否领取',
  pick_up_date   DATETIME     NULL COMMENT '领取时间',
  sign_url       VARCHAR(255) NULL COMMENT '申请人签名图片',
  reviewer_sign  VARCHAR(255) NULL COMMENT '审核人签名',
  feedback_url   VARCHAR(255) NULL COMMENT '反馈图片路径（实物图/现场照片）',
  feedback_at    DATETIME     NULL COMMENT '反馈时间',
  created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_apply_no (apply_no),
  KEY idx_user (user_id),
  KEY idx_status (status),
  CONSTRAINT fk_app_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='打印申请表';

-- ---------------------------------------------------------------
-- 3. 操作日志表 operation_logs
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operation_logs (
  id         INT         NOT NULL AUTO_INCREMENT COMMENT '主键',
  user_id    INT         NULL COMMENT '操作用户（可空）',
  action     VARCHAR(64) NOT NULL COMMENT '操作类型',
  detail     TEXT        NULL COMMENT '操作详情',
  ip         VARCHAR(64) NULL COMMENT '来源 IP',
  created_at DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
  PRIMARY KEY (id),
  KEY idx_user (user_id),
  CONSTRAINT fk_log_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='操作日志表';

-- ---------------------------------------------------------------
-- 可选：插入一条管理员账号示例（学号需在 config 的 ADMIN_STUDENT_IDS 中）
-- 实际管理员由 CAS 登录时按学号清单自动赋予角色，无需手工建号。
-- ---------------------------------------------------------------

-- ---------------------------------------------------------------
-- 4. 留言消息表 chat_messages（联系工作室）
--    会话以学生视角建模：user_id 恒为学生 users.id，
--    管理员回复时 sender_role='admin'。
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_messages (
  id           INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
  user_id      INT          NOT NULL COMMENT '会话归属学生（users.id）',
  sender_role  VARCHAR(8)   NOT NULL COMMENT '发送方角色 user/admin',
  sender_id    INT          NOT NULL COMMENT '实际发送人 users.id',
  content_type VARCHAR(8)   NOT NULL DEFAULT 'text' COMMENT 'text/image/video/voice/file',
  content      TEXT         NULL COMMENT '文字内容',
  file_url     VARCHAR(255) NULL COMMENT '附件相对路径（uploads/chat/...）',
  file_name    VARCHAR(255) NULL COMMENT '原始文件名',
  file_size    INT          NULL COMMENT '文件字节数',
  duration     INT          NULL COMMENT '语音/视频时长（秒）',
  is_read      TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '接收方是否已读',
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  KEY idx_user (user_id),
  KEY idx_read (is_read),
  CONSTRAINT fk_msg_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='留言消息表（联系工作室）';

-- ---------------------------------------------------------------
-- 5. 公告表 announcements（首页「最新通知」，管理员维护）
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS announcements (
  id           INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
  title        VARCHAR(128) NOT NULL COMMENT '标题',
  content      TEXT         NOT NULL COMMENT '正文（纯文本，保留换行）',
  publisher_id INT          NULL COMMENT '发布管理员（users.id）',
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '发布时间',
  updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  KEY idx_pub (publisher_id),
  CONSTRAINT fk_notice_pub FOREIGN KEY (publisher_id) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='公告表（最新通知）';

-- ---------------------------------------------------------------
-- 6. 耗材台账 consumables + 流水 consumable_logs（管理端扫码维护）
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS consumables (
  id         INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
  barcode    VARCHAR(64)  NOT NULL COMMENT '条形码（一串数字）',
  name       VARCHAR(128) NOT NULL COMMENT '耗材名称',
  material   VARCHAR(64)  NULL COMMENT '材质（如 PLA/PETG/树脂）',
  color      VARCHAR(64)  NULL COMMENT '颜色',
  unit       VARCHAR(16)  NOT NULL DEFAULT '卷' COMMENT '计量单位',
  quantity   INT          NOT NULL DEFAULT 0 COMMENT '当前库存数量',
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '首次入库时间',
  updated_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_barcode (barcode)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='耗材台账';

CREATE TABLE IF NOT EXISTS consumable_logs (
  id             INT         NOT NULL AUTO_INCREMENT COMMENT '主键',
  consumable_id  INT         NOT NULL COMMENT '耗材（consumables.id）',
  action         VARCHAR(8)  NOT NULL COMMENT 'in=入库 open=拆封',
  quantity_change INT        NOT NULL COMMENT '数量变动（入库+n / 拆封-1）',
  quantity_after INT         NOT NULL COMMENT '操作后库存',
  operator_id    INT         NULL COMMENT '操作人（users.id）',
  note           VARCHAR(255) NULL COMMENT '备注',
  created_at     DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
  PRIMARY KEY (id),
  KEY idx_item (consumable_id),
  CONSTRAINT fk_clog_item FOREIGN KEY (consumable_id) REFERENCES consumables (id) ON DELETE CASCADE,
  CONSTRAINT fk_clog_op FOREIGN KEY (operator_id) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='耗材进出流水';

-- ---------------------------------------------------------------
-- 7. 站内通知 notifications（审批结果/新留言/新申请/耗材进出提醒）
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notifications (
  id         INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
  user_id    INT          NOT NULL COMMENT '接收人（users.id）',
  ntype      VARCHAR(16)  NOT NULL COMMENT 'approval/apply/chat/consumable',
  title      VARCHAR(128) NOT NULL COMMENT '标题',
  body       VARCHAR(255) NULL COMMENT '详情',
  link       VARCHAR(128) NULL COMMENT '点击跳转的前端路径',
  is_read    TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否已读',
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  KEY idx_user (user_id),
  KEY idx_read (is_read),
  CONSTRAINT fk_notice_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='站内通知';
