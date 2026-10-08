-- 补建缺失的三张表（耗材/流水/通知）
-- 用法：mysql -uroot -p hust_3d < create_missing_tables.sql
-- 或在 Navicat 中打开 hust_3d 库后整体执行

CREATE TABLE IF NOT EXISTS consumables (
  id         INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
  barcode    VARCHAR(64)  NOT NULL COMMENT '条形码',
  name       VARCHAR(128) NOT NULL COMMENT '耗材名称',
  material   VARCHAR(64)  NULL COMMENT '材质',
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
  consumable_id  INT         NOT NULL COMMENT '耗材',
  action         VARCHAR(8)  NOT NULL COMMENT 'in=入库 open=拆封',
  quantity_change INT        NOT NULL COMMENT '数量变动',
  quantity_after INT         NOT NULL COMMENT '操作后库存',
  operator_id    INT         NULL COMMENT '操作人',
  note           VARCHAR(255) NULL COMMENT '备注',
  created_at     DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
  PRIMARY KEY (id),
  KEY idx_item (consumable_id),
  CONSTRAINT fk_clog_item FOREIGN KEY (consumable_id) REFERENCES consumables (id) ON DELETE CASCADE,
  CONSTRAINT fk_clog_op FOREIGN KEY (operator_id) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='耗材进出流水';

CREATE TABLE IF NOT EXISTS notifications (
  id         INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
  user_id    INT          NOT NULL COMMENT '接收人',
  ntype      VARCHAR(16)  NOT NULL COMMENT 'approval/apply/chat/consumable',
  title      VARCHAR(128) NOT NULL COMMENT '标题',
  body       VARCHAR(255) NULL COMMENT '详情',
  link       VARCHAR(128) NULL COMMENT '点击跳转路径',
  is_read    TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否已读',
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (id),
  KEY idx_user (user_id),
  KEY idx_read (is_read),
  CONSTRAINT fk_notice_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='站内通知';

SHOW TABLES;
