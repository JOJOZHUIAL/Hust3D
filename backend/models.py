# -*- coding: utf-8 -*-
"""数据库模型（与 sql/schema.sql 保持一致）。

说明：本文件用于 SQLAlchemy ORM；纯 SQL 建表脚本见 sql/schema.sql。
两者字段一一对应，请同步维护。
"""
from datetime import datetime
from extensions import db


def _fmt(dt):
    """统一时间输出格式（None 安全）。"""
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


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
    remark = db.Column(db.Text, nullable=True, comment="特别说明")
    status = db.Column(db.String(16), nullable=False, default="pending",
                       comment="pending/approved/rejected/printing/completed/cancelled")
    admin_comment = db.Column(db.Text, nullable=True, comment="审批意见/拒绝原因")
    reviewed_at = db.Column(db.DateTime, nullable=True)
    printed_at = db.Column(db.DateTime, nullable=True)
    picked_up = db.Column(db.Boolean, nullable=False, default=False, comment="是否领取")
    pick_up_date = db.Column(db.DateTime, nullable=True)
    sign_url = db.Column(db.String(255), nullable=True, comment="申请人签名图片")
    reviewer_sign = db.Column(db.String(255), nullable=True, comment="审核人签名")
    feedback_url = db.Column(db.String(255), nullable=True, comment="反馈图片路径（实物图/现场照片）")
    feedback_at = db.Column(db.DateTime, nullable=True, comment="反馈时间")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

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
            "remark": self.remark,
            "status": self.status,
            "admin_comment": self.admin_comment,
            "reviewed_at": _fmt(self.reviewed_at),
            "printed_at": _fmt(self.printed_at),
            "picked_up": self.picked_up,
            "pick_up_date": _fmt(self.pick_up_date),
            "sign_url": self.sign_url,
            "reviewer_sign": self.reviewer_sign,
            "feedback_url": self.feedback_url,
            "feedback_at": _fmt(self.feedback_at),
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
            }
        return d

    def timeline(self):
        """构造状态时间线，前端直接渲染（提交→审批→打印→领取）。"""
        steps = [{"title": "提交申请", "time": _fmt(self.created_at)}]
        if self.reviewed_at is not None:
            title = "审批驳回" if self.status == "rejected" else "审批通过"
            steps.append({"title": title, "time": _fmt(self.reviewed_at)})
        if self.printed_at is not None:
            steps.append({"title": "开始打印", "time": _fmt(self.printed_at)})
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


class Notification(db.Model):
    """站内通知：审批结果 / 新留言 / 新申请 / 耗材进出等事件的提醒，全员各自收各自的。"""

    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True,
                        comment="接收人（users.id）")
    ntype = db.Column(db.String(16), nullable=False,
                      comment="类型 approval=审批结果 apply=新申请 chat=留言 consumable=耗材")
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


class OperationLog(db.Model):
    """操作日志表：记录关键操作（登录、提交、审批、状态变更等）。"""

    __tablename__ = "operation_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    action = db.Column(db.String(64), nullable=False, comment="操作类型")
    detail = db.Column(db.Text, nullable=True, comment="操作详情")
    ip = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
