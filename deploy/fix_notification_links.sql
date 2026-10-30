-- 一次性修复：旧版「反馈待审核」通知的跳转链接指向 /admin/pending，
-- 按通知标题里的申请编号匹配申请单，把链接改写为该申请的详情页（审核页）。
-- 用法（服务器上，注意 --default-character-set 防 GBK 乱码）：
--   mysql --default-character-set=utf8mb4 -uroot -p hust_3d < fix_notification_links.sql
-- 可重复执行（已改过的链接不再匹配 WHERE 条件，等于幂等）。

-- 1) 反馈类通知：link 改为该申请的详情页（标题形如「新反馈待审核 HUST3D20261026003」）
UPDATE notifications n
JOIN print_applications p
  ON n.title LIKE CONCAT('%', p.apply_no)
SET n.link = CONCAT('/application/', p.id)
WHERE n.ntype = 'feedback'
  AND n.link = '/admin/pending';

-- 2) 新申请通知：补上 cat=pending，点击后落在「待审批」分组（可选，不改也只是默认就是它）
UPDATE notifications
SET link = '/admin/pending?cat=pending'
WHERE ntype = 'apply'
  AND link = '/admin/pending';

-- 执行后核对（可选）：SELECT ntype, link, COUNT(*) FROM notifications WHERE link LIKE '%pending%' GROUP BY ntype, link;
