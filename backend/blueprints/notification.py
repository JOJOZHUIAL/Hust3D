# -*- coding: utf-8 -*-
"""站内通知接口：列表 / 未读数 / 已读 / 取件提醒。

取件提醒（ntype=pickup）单独一组接口，供首页弹窗使用：
  GET  /api/notification/pickup       待确认的取件提醒（含申请信息）
  POST /api/notification/pickup/ack   确认已看到（标记已读，弹窗不再出现）
"""
from flask import Blueprint, request, g

from extensions import db
from models import Notification, PrintApplication
from utils.response import ok, fail
from utils.auth import login_required

bp = Blueprint("notification", __name__)

# 允许按类型标记已读的通知类型
NOTIFY_TYPES = {"approval", "apply", "chat", "consumable", "status", "pickup"}

# 取件提醒只对「还在等学生来取」的申请有意义
PICKUP_KEEP_STATUS = ("completed",)


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _app_id_from_link(link):
    """从 link（形如 /application/12）里取出申请 id。"""
    try:
        return int((link or "").rstrip("/").split("/")[-1])
    except (TypeError, ValueError):
        return None


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


@bp.route("/read-type/<ntype>", methods=["POST"])
@login_required
def read_type(ntype):
    """按类型标记已读（进入对应页面时调用，红点联动）。

    返回剩余未读数，前端直接更新角标。
    """
    if ntype not in NOTIFY_TYPES:
        return fail("无效的通知类型", code=1002)
    Notification.query.filter_by(user_id=g.user.id, ntype=ntype, is_read=False) \
        .update({"is_read": True}, synchronize_session=False)
    db.session.commit()
    remain = Notification.query.filter_by(user_id=g.user.id, is_read=False).count()
    return ok({"count": remain})


@bp.route("/read-all", methods=["POST"])
@login_required
def read_all():
    """全部已读。"""
    Notification.query.filter_by(user_id=g.user.id, is_read=False) \
        .update({"is_read": True}, synchronize_session=False)
    db.session.commit()
    return ok(msg="全部已读")


@bp.route("/pickup", methods=["GET"])
@login_required
def pickup_pending():
    """待确认的取件提醒（首页弹窗用）。

    只返回「未读 + 对应申请仍在等待领取」的提醒；已经领取、被取消或状态已变化的
    会顺手标记已读，避免弹窗反复出现又关不掉。
    """
    rows = (
        Notification.query.filter_by(user_id=g.user.id, ntype="pickup", is_read=False)
        .order_by(Notification.id.desc())
        .all()
    )
    items, stale = [], []
    for r in rows:
        app_obj = None
        app_id = _app_id_from_link(r.link)
        if app_id:
            app_obj = db.session.get(PrintApplication, app_id)
        if (
            app_obj is None
            or app_obj.user_id != g.user.id
            or app_obj.picked_up
            or app_obj.status not in PICKUP_KEEP_STATUS
        ):
            stale.append(r)
            continue
        d = r.to_dict()
        d["application"] = {
            "id": app_obj.id,
            "apply_no": app_obj.apply_no,
            "file_name": app_obj.file_name,
            "material": app_obj.material,
            "model_count": app_obj.model_count,
            "completed_at": _fmt(app_obj.completed_at),
            "picked_up": bool(app_obj.picked_up),
        }
        items.append(d)

    if stale:
        for r in stale:
            r.is_read = True
        db.session.commit()

    return ok({"count": len(items), "items": items})


@bp.route("/pickup/ack", methods=["POST"])
@login_required
def pickup_ack():
    """确认取件提醒（首页弹窗「我知道了」）。

    传 ids 只确认指定的几条；不传则确认该用户全部待确认的取件提醒。
    返回剩余未读数，前端直接更新角标。
    """
    data = request.get_json(silent=True) or {}
    raw_ids = data.get("ids")
    q = Notification.query.filter_by(user_id=g.user.id, ntype="pickup", is_read=False)
    if isinstance(raw_ids, list) and raw_ids:
        ids = [int(i) for i in raw_ids if str(i).isdigit()]
        if not ids:
            return ok({"acked": 0, "count": _unread(g.user.id)}, msg="已确认")
        q = q.filter(Notification.id.in_(ids))
    acked = q.update({"is_read": True}, synchronize_session=False)
    db.session.commit()
    return ok({"acked": acked, "count": _unread(g.user.id)}, msg="已确认")


def _unread(user_id):
    return Notification.query.filter_by(user_id=user_id, is_read=False).count()
