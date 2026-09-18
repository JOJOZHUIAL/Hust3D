# -*- coding: utf-8 -*-
"""用户信息与配额。"""
from flask import Blueprint, g, current_app
from extensions import db
from utils.response import ok
from utils.auth import login_required
from services.quota import ensure_quota

bp = Blueprint("user", __name__)


@bp.route("/info", methods=["GET"])
@login_required
def info():
    """获取当前用户信息（含剩余配额，先做学期刷新）。"""
    user = g.user
    ensure_quota(user)
    db.session.commit()
    return ok(user.to_dict())


@bp.route("/quota", methods=["GET"])
@login_required
def quota():
    """获取剩余打印次数。"""
    user = g.user
    remaining = ensure_quota(user)
    db.session.commit()
    return ok({
        "remaining": remaining,
        "semester": user.semester,
        "total": current_app.config["DEFAULT_QUOTA"],
    })
