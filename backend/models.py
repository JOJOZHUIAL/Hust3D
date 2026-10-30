# -*- coding: utf-8 -*-
"""数据库模型（与 sql/schema.sql 保持一致）。

说明：本文件用于 SQLAlchemy ORM；纯 SQL 建表脚本见 sql/schema.sql。
两者字段一一对应，请同步维护。
"""
from datetime import datetime, timedelta

from flask import current_app

from extensions import db

# 反馈超时天数兜底值（真正生效的取配置 FEEDBACK_EXPIRE_DAYS）
DEFAULT_FEEDBACK_EXPIRE_DAYS = 7


def _fmt(dt):
    """统一时间输出格式（None 安全）。"""
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def feedback_expire_days():
    """读取「打印完成后多少天未反馈即过期」配置，异常时退回 7 天。"""
    try:
        return int(current_app.config.get("FEEDBACK_EXPIRE_DAYS", DEFAULT_FEEDBACK_EXPIRE_DAYS))
    except (RuntimeError, TypeError, ValueError):  # 无应用上下文 / 配置非法
        return DEFAULT_FEEDBACK_EXPIRE_DAYS


def _person_label(info):
    """把 {name, student_id} 拼成「张三（2023010101）」样式，缺字段时降级。"""
    if not info:
        return None
    name = (info.get("name") or "").strip()
    sid = (info.get("student_id") or "").strip()
    if name and sid:
        return f"{name}（{sid}）"
    return name or sid or None


def _basename(url):
    """从相对路径里取文件名（STL 原始文件名缺失时的兜底展示）。"""
    if not url:
        return None
    return str(url).replace("\\", "/").split("/")[-1] or None


class User(db.Model):
    """用户表：学号为身份主键，教务系统登录后自动建号，含姓名/学院/配额。"""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(db.String(32), unique=True, nullable=False, index=True, comment="学号")
    name = db.Column(db.String(64), nullable=True, comment="姓名")
    college = db.Column(db.String(128), nullable=True, comment="学院")
    phone = db.Column(db.String(32), nullable=True, comment="联系方式")
    email = db.Column(db.String(128), nullable=True, comment="邮箱")
    role = db.Column(db.String(16), nullable=False, default="user", comment="角色 admin/user")
    is_shared_admin = db.Column(db.Boolean, nullable=False, default=False,
                                comment="公共管理员共享账号：操作时需另行登记实际操作人")
    semester = db.Column(db.String(32), nullable=True, comment="当前学期，如 2026-1")
    remaining_quota = db.Column(db.Integer, nullable=False, default=2, comment="本学期剩余打印次数")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    applications = db.relationship("PrintApplication", backref="user", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "student_id": self.student_id,
            "name": self.name,
            "college": self.college,
            "phone": self.phone,
            "email": self.email,
            "role": self.role,
            "is_shared_admin": bool(self.is_shared_admin),
            "semester": self.semester,
            "remaining_quota": self.remaining_quota,
            "created_at": _fmt(self.created_at),
            "updated_at": _fmt(self.updated_at),
        }


class PrintApplication(db.Model):
    """打印申请表：对应 Word 表单「附件1 3D打印服务申请表单」。"""

    __tablename__ = "print_applications"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    apply_no = db.Column(db.String(32), unique=True, nullable=False, index=True, comment="申请编号")
    purpose = db.Column(db.String(32), nullable=False, comment="打印用途")
    purpose_other = db.Column(db.String(255), nullable=True, comment="其他用途说明")
    material = db.Column(db.String(32), nullable=False, default="PLA", comment="期望材料")
    model_count = db.Column(db.Integer, nullable=False, default=1, comment="模型数量")
    file_url = db.Column(db.String(255), nullable=True, comment="STL 文件相对路径")
    file_name = db.Column(db.String(255), nullable=True, comment="STL 原始文件名（展示用）")
    remark = db.Column(db.Text, nullable=True, comment="特别说明")
    status = db.Column(db.String(16), nullable=False, default="pending",
                       comment="pending/approved/rejected/printing/completed/cancelled")
    admin_comment = db.Column(db.Text, nullable=True, comment="审批意见/拒绝原因")
    reviewed_at = db.Column(db.DateTime, nullable=True)
    # —— 审批人留痕（快照姓名/学号，管理员账号变动也不丢历史） ——
    reviewer_id = db.Column(db.Integer, nullable=True, comment="审批人 users.id")
    reviewer_name = db.Column(db.String(64), nullable=True, comment="审批人姓名快照")
    reviewer_student_id = db.Column(db.String(32), nullable=True, comment="审批人学号快照")
    printed_at = db.Column(db.DateTime, nullable=True)
    # —— 打印操作人留痕（记录「开始打印」是谁点的） ——
    printed_by_id = db.Column(db.Integer, nullable=True, comment="打印操作人 users.id")
    printed_by_name = db.Column(db.String(64), nullable=True, comment="打印操作人姓名快照")
    printed_by_student_id = db.Column(db.String(32), nullable=True, comment="打印操作人学号快照")
    # —— 打印机绑定与「进度 100% 自动完成」——
    printer_id = db.Column(db.Integer, nullable=True, comment="绑定的打印机 printers.id")
    printer_name = db.Column(db.String(64), nullable=True, comment="打印机名称快照")
    print_state = db.Column(db.String(16), nullable=True,
                            comment="最近观察到的打印机状态 RUNNING/FINISH…")
    print_progress = db.Column(db.Integer, nullable=True, comment="最近观察到的打印进度 0-100")
    print_actual_file = db.Column(db.String(255), nullable=True,
                                  comment="打印机当前上报的真实文件名（可能是别的申请）")
    print_matched = db.Column(db.Boolean, nullable=False, default=False,
                              comment="打印机当前文件是否就是本申请（按文件名里的申请编号匹配）")
    print_seen_running = db.Column(db.Boolean, nullable=False, default=False,
                                   comment="是否已确认打印机真的开始打印（防误判已完成）")
    completed_auto = db.Column(db.Boolean, nullable=False, default=False,
                               comment="是否由打印机进度自动标记完成")
    completed_at = db.Column(db.DateTime, nullable=True, comment="打印完成时间（反馈计时起点）")
    expired_at = db.Column(db.DateTime, nullable=True,
                           comment="反馈超时时间（状态仍为 completed，只是不能再反馈/发奖励）")
    sms_sent_at = db.Column(db.DateTime, nullable=True, comment="取件短信发送成功时间")
    sms_result = db.Column(db.String(255), nullable=True, comment="取件短信发送结果（成功/失败原因）")
    picked_up = db.Column(db.Boolean, nullable=False, default=False, comment="是否领取")
    pick_up_date = db.Column(db.DateTime, nullable=True)
    sign_url = db.Column(db.String(255), nullable=True, comment="申请人签名图片")
    reviewer_sign = db.Column(db.String(255), nullable=True, comment="审核人签名")
    feedback_url = db.Column(db.String(255), nullable=True, comment="反馈图片路径（第一张，作封面）")
    feedback_at = db.Column(db.DateTime, nullable=True, comment="反馈时间")
    feedback_reviewed = db.Column(db.Boolean, nullable=True, default=None,
                                  comment="反馈审核：None=无需审核(auto模式)或已拒绝 0=待审核 1=通过")
    feedback_rewarded = db.Column(db.Boolean, nullable=False, default=False,
                                  comment="是否已发放反馈奖励（每单只发一次）")
    expected_feedback_at = db.Column(db.DateTime, nullable=True,
                                     comment="申请人自报的预计反馈时间")
    expected_feedback_note = db.Column(db.String(255), nullable=True,
                                       comment="不按默认期限时的原因说明")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    feedback_images = db.relationship(
        "FeedbackImage", backref="application", lazy="select",
        order_by="FeedbackImage.id", cascade="all, delete-orphan",
    )

    def to_dict(self):
        d = {
            "id": self.id,
            "user_id": self.user_id,
            "apply_no": self.apply_no,
            "purpose": self.purpose,
            "purpose_other": self.purpose_other,
            "material": self.material,
            "model_count": self.model_count,
            "file_url": self.file_url,
            "file_name": self.file_name or _basename(self.file_url),
            "remark": self.remark,
            "status": self.status,
            "admin_comment": self.admin_comment,
            "reviewed_at": _fmt(self.reviewed_at),
            "reviewer": self.reviewer_info(),
            "printed_at": _fmt(self.printed_at),
            "printed_by": self.printed_by_info(),
            "printer": self.printer_info(),
            "print_state": self.print_state,
            "print_progress": self.print_progress,
            "print_actual_file": self.print_actual_file,
            "print_matched": bool(self.print_matched),
            "print_seen_running": bool(self.print_seen_running),
            "completed_auto": bool(self.completed_auto),
            "completed_at": _fmt(self.completed_at),
            "expired_at": _fmt(self.expired_at),
            "expired": self.expired_at is not None,
            "sms_sent_at": _fmt(self.sms_sent_at),
            "sms_result": self.sms_result,
            "picked_up": self.picked_up,
            "pick_up_date": _fmt(self.pick_up_date),
            "sign_url": self.sign_url,
            "reviewer_sign": self.reviewer_sign,
            "feedback_url": self.feedback_url,
            "feedback_at": _fmt(self.feedback_at),
            "feedback_reviewed": self.feedback_reviewed,
            "feedback_rewarded": bool(self.feedback_rewarded),
            "feedback_images": [
                {"id": img.id, "url": img.url, "created_at": _fmt(img.created_at)}
                for img in (self.feedback_images or [])
            ],
            "feedback_deadline": _fmt(self.feedback_deadline()),
            "feedback_expire_days": feedback_expire_days(),
            "expected_feedback_at": _fmt(self.expected_feedback_at),
            "expected_feedback_note": self.expected_feedback_note,
            "can_withdraw": self.status == "pending",
            # 已完成的都能反馈：过期后也可补交，也能追加多张（奖励每单只发一次）
            "can_feedback": self.status == "completed",
            "created_at": _fmt(self.created_at),
            "updated_at": _fmt(self.updated_at),
            "timeline": self.timeline(),
        }
        # 附带申请人信息，详情页/管理员列表直接可用
        if self.user is not None:
            d["applicant"] = {
                "name": self.user.name,
                "student_id": self.user.student_id,
                "college": self.user.college,
                "phone": self.user.phone,
                "email": self.user.email,
            }
        return d

    # —— 审批人 / 打印操作人：输出成 {id, name, student_id}，前端直接展示 ——
    def reviewer_info(self):
        """审批人信息（姓名+学号快照），未审批时为 None。"""
        if not (self.reviewer_id or self.reviewer_name or self.reviewer_student_id):
            return None
        return {
            "id": self.reviewer_id,
            "name": self.reviewer_name,
            "student_id": self.reviewer_student_id,
        }

    def printed_by_info(self):
        """打印操作人信息（姓名+学号快照），未开始打印时为 None。"""
        if not (self.printed_by_id or self.printed_by_name or self.printed_by_student_id):
            return None
        return {
            "id": self.printed_by_id,
            "name": self.printed_by_name,
            "student_id": self.printed_by_student_id,
        }

    def printer_info(self):
        """绑定的打印机信息，未绑定时为 None。"""
        if not (self.printer_id or self.printer_name):
            return None
        return {"id": self.printer_id, "name": self.printer_name}

    def completed_base_time(self):
        """反馈计时基准：打印完成时间 →（老数据兜底）开始打印时间 → 最后更新时间。"""
        return self.completed_at or self.printed_at or self.updated_at

    def feedback_deadline(self):
        """反馈截止时间：完成时间 + FEEDBACK_EXPIRE_DAYS 天；无基准时间时为 None。"""
        base = self.completed_base_time()
        return base + timedelta(days=feedback_expire_days()) if base else None

    def timeline(self):
        """构造状态时间线，前端直接渲染（提交→审批→打印→完成→领取）。

        操作人（审批人/打印人）单独放在 operator 字段，前端只给管理员展示；
        打印机名称放在 printer 字段，学生也能看到（便于核对打印件）。
        """
        steps = [{"title": "提交申请", "time": _fmt(self.created_at)}]
        if self.reviewed_at is not None:
            title = "审批驳回" if self.status == "rejected" else "审批通过"
            steps.append({
                "title": title,
                "time": _fmt(self.reviewed_at),
                "operator": _person_label(self.reviewer_info()),
            })
        if self.printed_at is not None:
            steps.append({
                "title": "开始打印",
                "time": _fmt(self.printed_at),
                "operator": _person_label(self.printed_by_info()),
                "printer": self.printer_name,
            })
        if self.completed_at is not None:
            steps.append({
                "title": "打印完成",
                "time": _fmt(self.completed_at),
                "note": "打印机进度 100%，自动完成" if self.completed_auto else None,
            })
        if self.expired_at is not None:
            steps.append({"title": "反馈超时过期", "time": _fmt(self.expired_at)})
        if self.picked_up:
            steps.append({"title": "已领取", "time": _fmt(self.pick_up_date)})
        return steps


class ChatMessage(db.Model):
    """留言消息：学生与工作室的聊天记录，支持文字/图片/视频/语音/文件。

    会话以学生视角建模：user_id 恒为学生的用户 id，
    管理员回复时 sender_role='admin'、sender_id 为管理员用户 id。
    """

    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True,
                        comment="会话归属学生（users.id）")
    sender_role = db.Column(db.String(8), nullable=False, comment="发送方角色 user/admin")
    sender_id = db.Column(db.Integer, nullable=False, comment="实际发送人 users.id")
    content_type = db.Column(db.String(8), nullable=False, default="text",
                             comment="text/image/video/voice/file")
    content = db.Column(db.Text, nullable=True, comment="文字内容")
    file_url = db.Column(db.String(255), nullable=True, comment="附件相对路径（uploads/chat/...）")
    file_name = db.Column(db.String(255), nullable=True, comment="原始文件名")
    file_size = db.Column(db.Integer, nullable=True, comment="文件字节数")
    duration = db.Column(db.Integer, nullable=True, comment="语音/视频时长（秒）")
    is_read = db.Column(db.Boolean, nullable=False, default=False, comment="接收方是否已读")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "sender_role": self.sender_role,
            "sender_id": self.sender_id,
            "content_type": self.content_type,
            "content": self.content,
            "file_url": self.file_url,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "duration": self.duration,
            "is_read": self.is_read,
            "created_at": _fmt(self.created_at),
        }


class Announcement(db.Model):
    """公告/通知：管理员发布与维护，全员可见（首页「最新通知」）。"""

    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(128), nullable=False, comment="标题")
    content = db.Column(db.Text, nullable=False, comment="正文（纯文本，保留换行）")
    publisher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True,
                             comment="发布管理员（users.id，可空）")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    publisher = db.relationship("User", lazy=True)

    def to_dict(self, with_content=True):
        d = {
            "id": self.id,
            "title": self.title,
            "publisher": self.publisher.name if self.publisher else "工作室",
            "created_at": _fmt(self.created_at),
            "updated_at": _fmt(self.updated_at),
        }
        if with_content:
            d["content"] = self.content
        return d


class Consumable(db.Model):
    """耗材台账：条形码唯一标识一件耗材（如一卷 PLA），记录当前库存。"""

    __tablename__ = "consumables"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    barcode = db.Column(db.String(64), unique=True, nullable=False, index=True, comment="条形码（一串数字）")
    name = db.Column(db.String(128), nullable=False, comment="耗材名称")
    material = db.Column(db.String(64), nullable=True, comment="材质（如 PLA/PETG/树脂）")
    color = db.Column(db.String(64), nullable=True, comment="颜色")
    unit = db.Column(db.String(16), nullable=False, default="卷", comment="计量单位")
    quantity = db.Column(db.Integer, nullable=False, default=0, comment="当前库存数量")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now, comment="首次入库时间")
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    logs = db.relationship("ConsumableLog", backref="consumable", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "barcode": self.barcode,
            "name": self.name,
            "material": self.material,
            "color": self.color,
            "unit": self.unit,
            "quantity": self.quantity,
            "created_at": _fmt(self.created_at),
            "updated_at": _fmt(self.updated_at),
        }


class ConsumableLog(db.Model):
    """耗材流水：入库/拆封等操作记录，进出有据可查。"""

    __tablename__ = "consumable_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    consumable_id = db.Column(db.Integer, db.ForeignKey("consumables.id"), nullable=False, index=True)
    action = db.Column(db.String(8), nullable=False, comment="in=入库 open=拆封")
    quantity_change = db.Column(db.Integer, nullable=False, comment="数量变动（入库+n / 拆封-1）")
    quantity_after = db.Column(db.Integer, nullable=False, comment="操作后库存")
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, comment="操作人（users.id）")
    note = db.Column(db.String(255), nullable=True, comment="备注")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now, comment="操作时间")

    operator = db.relationship("User", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "consumable_id": self.consumable_id,
            "barcode": self.consumable.barcode if self.consumable else None,
            "name": self.consumable.name if self.consumable else None,
            "material": self.consumable.material if self.consumable else None,
            "color": self.consumable.color if self.consumable else None,
            "unit": self.consumable.unit if self.consumable else None,
            "action": self.action,
            "quantity_change": self.quantity_change,
            "quantity_after": self.quantity_after,
            "operator": self.operator.name if self.operator else None,
            "operator_id": self.operator_id,
            "note": self.note,
            "created_at": _fmt(self.created_at),
        }


class Printer(db.Model):
    """拓竹 3D 打印机：局域网 MQTT 直连，访问码即打印机屏上显示的访问码。"""

    __tablename__ = "printers"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(64), nullable=False, comment="打印机名称")
    ip = db.Column(db.String(64), nullable=False, comment="打印机局域网 IP")
    access_code = db.Column(db.String(64), nullable=False, comment="访问码")
    serial = db.Column(db.String(64), nullable=True, comment="序列号（MQTT 连接后自动发现）")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "ip": self.ip,
            "access_code": self.access_code,
            "serial": self.serial,
            "created_at": _fmt(self.created_at),
        }


class EmailMessage(db.Model):
    """邮件发送记录（管理端「消息通知 → 发送」的邮件通道）。"""

    __tablename__ = "email_messages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    to_addr = db.Column(db.String(128), nullable=False, comment="收件邮箱")
    subject = db.Column(db.String(255), nullable=False, comment="主题")
    body = db.Column(db.Text, nullable=False, comment="正文")
    status = db.Column(db.String(16), nullable=False, default="sent", index=True,
                       comment="sent=已发送 / failed=失败")
    error = db.Column(db.Text, nullable=True, comment="失败原因")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "to": self.to_addr,
            "subject": self.subject,
            "body": self.body,
            "status": self.status,
            "error": self.error,
            "created_at": _fmt(self.created_at),
        }


class Notification(db.Model):
    """站内通知：审批结果 / 新留言 / 新申请 / 耗材进出等事件的提醒，全员各自收各自的。"""

    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True,
                        comment="接收人（users.id）")
    ntype = db.Column(db.String(16), nullable=False,
                      comment="类型 approval=审批结果 apply=新申请 chat=留言 consumable=耗材 "
                              "status=状态变更 pickup=取件提醒")
    title = db.Column(db.String(128), nullable=False, comment="标题")
    body = db.Column(db.String(255), nullable=True, comment="详情（可空）")
    link = db.Column(db.String(128), nullable=True, comment="点击跳转的前端路径")
    is_read = db.Column(db.Boolean, nullable=False, default=False, comment="是否已读")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "ntype": self.ntype,
            "title": self.title,
            "body": self.body,
            "link": self.link,
            "is_read": self.is_read,
            "created_at": _fmt(self.created_at),
        }


class FeedbackImage(db.Model):
    """反馈图片（一单可多张，也可以事后追加 —— 学生不满意可重新上传）。"""

    __tablename__ = "application_feedback_images"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    application_id = db.Column(db.Integer, db.ForeignKey("print_applications.id"),
                               nullable=False, index=True, comment="申请 id")
    url = db.Column(db.String(255), nullable=False, comment="图片相对路径 uploads/feedback/..")
    uploader_id = db.Column(db.Integer, nullable=True, comment="上传人 users.id")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "application_id": self.application_id,
            "url": self.url,
            "created_at": _fmt(self.created_at),
        }


class AppRelease(db.Model):
    """安卓 App 发布包：管理后台上传 APK，客户端启动时据此提示更新。

    版本号用递增的整数 version_code 比较（对应安卓 build.gradle 里的 versionCode），
    只有上传的 version_code 大于客户端当前已安装的值时才会弹更新提示。
    """

    __tablename__ = "app_releases"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    version_code = db.Column(db.Integer, nullable=False, unique=True,
                             comment="版本号（递增整数，对应安卓 versionCode）")
    version_name = db.Column(db.String(32), nullable=True, comment="版本名称，如 1.3")
    file_url = db.Column(db.String(255), nullable=False, comment="APK 相对路径 uploads/apk/..")
    file_name = db.Column(db.String(255), nullable=True, comment="上传时的原始文件名")
    file_size = db.Column(db.Integer, nullable=True, comment="文件字节数")
    note = db.Column(db.Text, nullable=True, comment="更新说明")
    publisher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True,
                             comment="上传管理员 users.id")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    publisher = db.relationship("User", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "version_code": self.version_code,
            "version_name": self.version_name,
            "file_url": self.file_url,
            "file_name": self.file_name,
            "file_size": self.file_size,
            "size_text": f"{self.file_size / 1024 / 1024:.1f} MB" if self.file_size else None,
            "note": self.note,
            "publisher": self.publisher.name if self.publisher else None,
            "created_at": _fmt(self.created_at),
        }


class SmsMessage(db.Model):
    """短信发送记录 + 待发队列（同一张表）。

    手机上的短信网关（SmsForwarder）不一定总在线（手机是个人机，可能不在协会网络里），
    所以短信统一先落库：立即尝试发送，连不上网关就留在 pending，由后台线程定时重试，
    等手机回到局域网时自动补发。
    """

    __tablename__ = "sms_messages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    phone = db.Column(db.String(20), nullable=False, comment="接收手机号")
    content = db.Column(db.Text, nullable=False, comment="短信正文")
    kind = db.Column(db.String(20), nullable=False, default="custom",
                     comment="类型：pickup=取件通知，custom=管理员自定义，test=测试")
    application_id = db.Column(db.Integer, nullable=True, comment="关联申请 id（取件通知用）")
    apply_no = db.Column(db.String(40), nullable=True, comment="申请编号快照")
    receiver_name = db.Column(db.String(64), nullable=True, comment="收件人姓名快照")
    status = db.Column(db.String(16), nullable=False, default="pending", index=True,
                       comment="pending=待发送 / sent=已发送 / failed=失败")
    attempts = db.Column(db.Integer, nullable=False, default=0, comment="已尝试次数")
    last_error = db.Column(db.String(255), nullable=True, comment="最后一次失败原因")
    gateway = db.Column(db.String(255), nullable=True, comment="发送时使用的网关地址")
    sender_id = db.Column(db.Integer, nullable=True, comment="发起的管理员 users.id（自定义短信）")
    sender_name = db.Column(db.String(64), nullable=True, comment="发起管理员姓名快照")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now, index=True)
    sent_at = db.Column(db.DateTime, nullable=True, comment="发送成功时间")
    next_retry_at = db.Column(db.DateTime, nullable=True, comment="下次重试时间（网关不可达时）")

    def to_dict(self):
        return {
            "id": self.id,
            "phone": self.phone,
            "content": self.content,
            "kind": self.kind,
            "application_id": self.application_id,
            "apply_no": self.apply_no,
            "receiver_name": self.receiver_name,
            "status": self.status,
            "attempts": self.attempts,
            "last_error": self.last_error,
            "gateway": self.gateway,
            "sender_name": self.sender_name,
            "created_at": _fmt(self.created_at),
            "sent_at": _fmt(self.sent_at),
            "next_retry_at": _fmt(self.next_retry_at),
        }


class OperationLog(db.Model):
    """操作日志表：记录关键操作（登录、提交、审批、状态变更等）。"""

    __tablename__ = "operation_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    action = db.Column(db.String(64), nullable=False, comment="操作类型")
    detail = db.Column(db.Text, nullable=True, comment="操作详情")
    ip = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
