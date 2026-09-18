# -*- coding: utf-8 -*-
"""公告模块：首页「最新通知」的列表/详情（全员）与新建/编辑/删除（管理员）。"""
from datetime import datetime

from flask import Blueprint, request, g
from extensions import db
from models import Announcement
from utils.response import ok, fail
from utils.auth import login_required, admin_required
from services.logger import log_action

bp = Blueprint("notice", __name__)

TITLE_MAX = 100
CONTENT_MAX = 10000


def _check_payload(data):
    """校验标题与正文，返回规范化后的值（不通过返回 None）。"""
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    if not title or len(title) > TITLE_MAX:
        return None
    if not content or len(content) > CONTENT_MAX:
        return None
    return title, content


@bp.route("/list", methods=["GET"])
@login_required
def list_notices():
    """公告列表（最新在前，最多 50 条；不含正文，列表页轻量）。"""
    rows = (
        db.session.query(Announcement)
        .order_by(Announcement.created_at.desc())
        .limit(50)
        .all()
    )
    return ok([r.to_dict(with_content=False) for r in rows])


@bp.route("/<int:notice_id>", methods=["GET"])
@login_required
def detail(notice_id):
    """公告详情（含正文）。"""
    row = db.session.get(Announcement, notice_id)
    if row is None:
        return fail("公告不存在", code=404, http_status=404)
    return ok(row.to_dict())


@bp.route("/create", methods=["POST"])
@admin_required
def create():
    """新建公告（管理员）。"""
    data = request.get_json(silent=True) or {}
    parsed = _check_payload(data)
    if parsed is None:
        return fail("标题（≤100字）与正文（≤10000字）不能为空", code=1002)
    title, content = parsed
    row = Announcement(title=title, content=content, publisher_id=g.user.id)
    db.session.add(row)
    log_action(g.user.id, "notice_create", f"发布公告「{title}」")
    db.session.commit()
    return ok(row.to_dict(), msg="发布成功")


@bp.route("/update", methods=["PUT"])
@admin_required
def update():
    """编辑公告（管理员）。"""
    data = request.get_json(silent=True) or {}
    row = db.session.get(Announcement, data.get("id"))
    if row is None:
        return fail("公告不存在", code=404, http_status=404)
    parsed = _check_payload(data)
    if parsed is None:
        return fail("标题（≤100字）与正文（≤10000字）不能为空", code=1002)
    row.title, row.content = parsed
    row.updated_at = datetime.now()
    log_action(g.user.id, "notice_update", f"编辑公告「{row.title}」")
    db.session.commit()
    return ok(row.to_dict(), msg="保存成功")


@bp.route("/delete/<int:notice_id>", methods=["DELETE"])
@admin_required
def delete(notice_id):
    """删除公告（管理员）。"""
    row = db.session.get(Announcement, notice_id)
    if row is None:
        return fail("公告不存在", code=404, http_status=404)
    db.session.delete(row)
    log_action(g.user.id, "notice_delete", f"删除公告「{row.title}」")
    db.session.commit()
    return ok(msg="删除成功")
