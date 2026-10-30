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
  file_name      VARCHAR(255) NULL COMMENT 'STL 原始文件名（展示用）',
  remark         TEXT         NULL COMMENT '特别说明',
  status         VARCHAR(16)  NOT NULL DEFAULT 'pending' COMMENT 'pending/approved/rejected/printing/completed/cancelled（过期不是状态，见 expired_at）',
  admin_comment  TEXT         NULL COMMENT '审批意见/拒绝原因',
  reviewed_at    DATETIME     NULL COMMENT '审批时间',
  reviewer_id    INT          NULL COMMENT '审批人 users.id',
  reviewer_name  VARCHAR(64)  NULL COMMENT '审批人姓名快照',
  reviewer_student_id VARCHAR(32) NULL COMMENT '审批人学号快照',
  printed_at     DATETIME     NULL COMMENT '开始打印时间',
  printed_by_id  INT          NULL COMMENT '打印操作人 users.id',
  printed_by_name VARCHAR(64) NULL COMMENT '打印操作人姓名快照',
  printed_by_student_id VARCHAR(32) NULL COMMENT '打印操作人学号快照',
  printer_id     INT          NULL COMMENT '绑定的打印机 printers.id',
  printer_name   VARCHAR(64)  NULL COMMENT '打印机名称快照',
  print_state    VARCHAR(16)  NULL COMMENT '最近观察到的打印机状态 RUNNING/FINISH',
  print_progress INT          NULL COMMENT '最近观察到的打印进度 0-100',
  print_actual_file VARCHAR(255) NULL COMMENT '打印机当前上报的真实文件名（可能是别的申请）',
  print_matched  TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '打印机当前文件是否就是本申请',
  print_seen_running TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否已确认打印机真的开始打印',
  completed_auto TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否由打印机进度自动标记完成',
  completed_at   DATETIME     NULL COMMENT '打印完成时间（反馈计时起点）',
  expired_at     DATETIME     NULL COMMENT '反馈超时时间（状态仍为 completed，只是不能再反馈/发奖励）',
  sms_sent_at    DATETIME     NULL COMMENT '取件短信发送成功时间',
  sms_result     VARCHAR(255) NULL COMMENT '取件短信发送结果（成功/失败原因）',
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

-- ---------------------------------------------------------------
-- 8. 打印机表 printers（拓竹 MQTT 监视）+ 反馈审核列迁移
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS printers (
  id          INT         NOT NULL AUTO_INCREMENT COMMENT '主键',
  name        VARCHAR(64) NOT NULL COMMENT '打印机名称',
  ip          VARCHAR(64) NOT NULL COMMENT '打印机局域网 IP',
  access_code VARCHAR(64) NOT NULL COMMENT '访问码',
  serial      VARCHAR(64) NULL COMMENT '序列号（MQTT 连接后自动发现）',
  created_at  DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='拓竹打印机';

-- ---------------------------------------------------------------
-- 9. App 发布包 app_releases（管理后台上传 APK，客户端据此提示更新）
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_releases (
  id           INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
  version_code INT          NOT NULL COMMENT '版本号（递增整数，对应安卓 versionCode）',
  version_name VARCHAR(32)  NULL COMMENT '版本名称，如 1.3',
  file_url     VARCHAR(255) NOT NULL COMMENT 'APK 相对路径 uploads/apk/...',
  file_name    VARCHAR(255) NULL COMMENT '原始文件名',
  file_size    INT          NULL COMMENT '文件字节数',
  note         TEXT         NULL COMMENT '更新说明',
  publisher_id INT          NULL COMMENT '上传管理员 users.id',
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '发布时间',
  PRIMARY KEY (id),
  UNIQUE KEY uk_version_code (version_code),
  KEY idx_pub (publisher_id),
  CONSTRAINT fk_release_pub FOREIGN KEY (publisher_id) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='App 发布包（版本更新）';

-- ---------------------------------------------------------------
-- 老库补列（新库已包含；老库也可直接启动后端由 app.py 自动补列）：
--   reviewer_id / reviewer_name / reviewer_student_id        审批人留痕
--   printed_by_id / printed_by_name / printed_by_student_id  打印操作人留痕
--   completed_at / expired_at                                完成时间 / 反馈过期时间
--   feedback_reviewed                                        反馈审核状态
--   file_name                                                STL 原始文件名
--   printer_id / printer_name / print_state / print_progress  打印机绑定与进度
--   print_actual_file / print_matched                        打印机真实文件与匹配结果
--   print_seen_running / completed_auto                      自动完成状态标记

-- ---------------------------------------------------------------
-- 10. 短信记录 / 待发队列 sms_messages
--     手机网关（SmsForwarder）不一定在线：短信先落库立即尝试，
--     连不上就留在 pending，后台线程每分钟重试，手机上线后自动补发。
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sms_messages (
  id             INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
  phone          VARCHAR(20)  NOT NULL COMMENT '接收手机号',
  content        TEXT         NOT NULL COMMENT '短信正文',
  kind           VARCHAR(20)  NOT NULL DEFAULT 'custom' COMMENT '类型：pickup=取件通知 / custom=管理员自定义 / test=测试',
  application_id INT          NULL COMMENT '关联申请 id（取件通知）',
  apply_no       VARCHAR(40)  NULL COMMENT '申请编号快照',
  receiver_name  VARCHAR(64)  NULL COMMENT '收件人姓名快照',
  status         VARCHAR(16)  NOT NULL DEFAULT 'pending' COMMENT 'pending=待发送 / sent=已发送 / failed=失败',
  attempts       INT          NOT NULL DEFAULT 0 COMMENT '已尝试次数',
  last_error     VARCHAR(255) NULL COMMENT '最后一次失败原因',
  gateway        VARCHAR(255) NULL COMMENT '发送时使用的网关地址',
  sender_id      INT          NULL COMMENT '发起管理员 users.id',
  sender_name    VARCHAR(64)  NULL COMMENT '发起管理员姓名快照',
  created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  sent_at        DATETIME     NULL COMMENT '发送成功时间',
  next_retry_at  DATETIME     NULL COMMENT '下次重试时间',
  PRIMARY KEY (id),
  KEY idx_sms_status (status),
  KEY idx_sms_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='短信发送记录与待发队列';

-- ---------------------------------------------------------------
-- 11. 反馈图片 application_feedback_images
--     一单可多张，也可以事后追加（学生不满意可重新上传）
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS application_feedback_images (
  id             INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
  application_id INT          NOT NULL COMMENT '申请 print_applications.id',
  url            VARCHAR(255) NOT NULL COMMENT '图片相对路径 uploads/feedback/..',
  uploader_id    INT          NULL COMMENT '上传人 users.id',
  created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '上传时间',
  PRIMARY KEY (id),
  KEY idx_fb_app (application_id),
  CONSTRAINT fk_fb_app FOREIGN KEY (application_id)
    REFERENCES print_applications (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='反馈图片（一单多张，可追加）';
