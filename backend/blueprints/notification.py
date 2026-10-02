# -*- coding: utf-8 -*-
"""站内通知接口：列表 / 未读数 / 已读。"""
from flask import Blueprint, request, g

from extensions import db
from models import Notification
from utils.response import ok, fail
from utils.auth import login_required

bp = Blueprint("notification", __name__)


@bp.route("/list", methods=["GET"])
@login_required
def list_notifications():
    """当前用户的通知（最新在前，最近 50 条）。"""
    rows = (
        Notification.query.filter_by(user_id=g.user.id)
        .order_by(Notification.id.desc())
        .limit(50)
        .all()
    )
    return ok([r.to_dict() for r in rows])


@bp.route("/unread-count", methods=["GET"])
@login_required
def unread_count():
    """未读通知数（前端轮询角标 + 横幅用）。"""
    cnt = Notification.query.filter_by(user_id=g.user.id, is_read=False).count()
    return ok({"count": cnt})


@bp.route("/read/<int:notice_id>", methods=["POST"])
@login_required
def read_one(notice_id):
    """标记单条已读。"""
    row = Notification.query.filter_by(id=notice_id, user_id=g.user.id).first()
    if row is None:
        return fail("通知不存在", code=404, http_status=404)
    row.is_read = True
    db.session.commit()
    return ok(msg="已读")


@bp.route("/read-all", methods=["POST"])
@login_required
def read_all():
    """全部已读。"""
    Notification.query.filter_by(user_id=g.user.id, is_read=False) \
        .update({"is_read": True}, synchronize_session=False)
    db.session.commit()
    return ok(msg="全部已读")
