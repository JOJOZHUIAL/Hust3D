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


def notify_admins(ntype, title, body="", link=""):
    """给全部管理员各发一条（管理员共享收件箱）。"""
    for u in User.query.filter_by(role="admin").all():
        notify_user(u.id, ntype, title, body, link)
