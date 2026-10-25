# -*- coding: utf-8 -*-
"""站内通知生成：各业务事件发生时写入 notifications 表。

只 add 不 commit，与业务变更同事务提交（与 logger 同约定）。
"""
from models import Notification, User
from extensions import db


def notify_user(user_id, ntype, title, body="", link=""):
    """给指定用户发一条通知。"""
    db.session.add(Notification(
        user_id=user_id, ntype=ntype,
        title=(title or "")[:128], body=(body or "")[:255], link=(link or "")[:128],
    ))


def notify_admins(ntype, title, body="", link="", exclude_uid=None):
    """给全部管理员各发一条（管理员共享收件箱），可排除某人（如发送者本人）。"""
    for u in User.query.filter(User.role.in_(("admin", "superadmin"))).all():
        if exclude_uid is not None and u.id == exclude_uid:
            continue
        notify_user(u.id, ntype, title, body, link)


def notify_pickup(app_obj, extra=""):
    """打印完成 → 取件提醒。

    ntype 用独立的 pickup：前端首页据此弹「请取件」弹窗，学生确认后把该条
    标记已读，弹窗就不再出现（不需要额外的已确认字段）。
    """
    body = f"{app_obj.file_name or '模型文件'} 已打印完成，请携带校园卡到工作室取件"
    if extra:
        body = f"{body}；{extra}"
    notify_user(
        app_obj.user_id, "pickup",
        f"打印完成，请取件 · {app_obj.apply_no}",
        body,
        link=f"/application/{app_obj.id}",
    )
