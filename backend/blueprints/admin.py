# -*- coding: utf-8 -*-
"""管理员端：待审批列表、审批（通过/拒绝）、打印状态更新。"""
from datetime import datetime

from flask import Blueprint, request, g
from sqlalchemy import or_
from extensions import db
from models import PrintApplication, User
from utils.response import ok, fail
from utils.auth import admin_required, super_required
from services.logger import log_action
from services.notify import notify_user

bp = Blueprint("admin", __name__)


@bp.route("/applications/pending", methods=["GET"])
@admin_required
def pending_list():
    """待审批列表：所有 pending 状态申请，按时间倒序。"""
    rows = (
        db.session.query(PrintApplication)
        .filter_by(status="pending")
        .order_by(PrintApplication.created_at.desc())
        .all()
    )
    return ok([r.to_dict() for r in rows])


@bp.route("/applications", methods=["GET"])
@admin_required
def all_list():
    """全部申请列表（可按状态筛选），供管理员查看与推进状态。"""
    status = request.args.get("status", "")
    q = db.session.query(PrintApplication)
    if status in {"pending", "approved", "rejected", "printing", "completed", "cancelled"}:
        q = q.filter_by(status=status)
    rows = q.order_by(PrintApplication.created_at.desc()).all()
    return ok([r.to_dict() for r in rows])


@bp.route("/application/review", methods=["POST"])
@admin_required
def review():
    """审批操作：通过 / 拒绝（拒绝必须填原因）。"""
    data = request.get_json(silent=True) or {}
    app_id = data.get("id")
    action = data.get("action")
    comment = (data.get("comment") or "").strip()
    reviewer_sign = data.get("reviewer_sign") or ""

    app_obj = db.session.get(PrintApplication, app_id)
    if app_obj is None:
        return fail("申请不存在", code=404, http_status=404)
    if app_obj.status != "pending":
        return fail("该申请已处理", code=1002)

    if action == "approve":
        app_obj.status = "approved"
        app_obj.admin_comment = comment or None
        notify_user(app_obj.user_id, "approval",
                    f"申请 {app_obj.apply_no} 已通过",
                    comment or "请等待打印，完成后凭校园卡到工作室领取",
                    link=f"/application/{app_obj.id}")
    elif action == "reject":
        if not comment:
            return fail("拒绝时请填写拒绝原因", code=1002)
        app_obj.status = "rejected"
        app_obj.admin_comment = comment
        notify_user(app_obj.user_id, "approval",
                    f"申请 {app_obj.apply_no} 未通过",
                    comment,
                    link=f"/application/{app_obj.id}")
    else:
        return fail("无效的审批操作", code=1002)

    app_obj.reviewer_sign = reviewer_sign or None
    app_obj.reviewed_at = datetime.now()
    log_action(g.user.id, "review", f"{action} 申请 {app_obj.apply_no}: {comment}")
    db.session.commit()
    return ok(app_obj.to_dict(), msg="操作成功")


@bp.route("/application/status", methods=["PUT"])
@admin_required
def update_status():
    """手动推进打印状态：已通过 → 打印中 → 已完成（可标记领取）。"""
    data = request.get_json(silent=True) or {}
    app_id = data.get("id")
    status = data.get("status")
    picked_up = bool(data.get("picked_up", False))

    if status not in {"printing", "completed", "cancelled"}:
        return fail("无效的状态", code=1002)

    app_obj = db.session.get(PrintApplication, app_id)
    if app_obj is None:
        return fail("申请不存在", code=404, http_status=404)

    app_obj.status = status
    if status == "printing":
        app_obj.printed_at = datetime.now()
        notify_user(app_obj.user_id, "status",
                    f"申请 {app_obj.apply_no} 已开始打印",
                    "打印完成后会通知你领取，请留意消息",
                    link=f"/application/{app_obj.id}")
    elif status == "completed":
        if picked_up:
            app_obj.picked_up = True
            app_obj.pick_up_date = datetime.now()
        notify_user(app_obj.user_id, "status",
                    f"申请 {app_obj.apply_no} 已完成",
                    "请上传实物图/现场照片反馈，成功可奖励 1 次打印机会",
                    link=f"/application/{app_obj.id}")

    log_action(g.user.id, "update_status", f"申请 {app_obj.apply_no} → {status}")
    db.session.commit()
    return ok(app_obj.to_dict(), msg="状态已更新")


@bp.route("/admins", methods=["GET"])
@super_required
def admins_list():
    """现任管理员清单（含超级管理员）。"""
    rows = User.query.filter(User.role.in_(("admin", "superadmin")))         .order_by(User.student_id.asc()).all()
    return ok([u.to_dict() for u in rows])


@bp.route("/users/search", methods=["GET"])
@super_required
def users_search():
    """按学号/姓名搜索普通用户（用于添加管理员）。"""
    kw = (request.args.get("keyword") or "").strip()
    if not kw:
        return ok([])
    like = f"%{kw}%"
    rows = User.query.filter(
        User.role == "user",
        or_(User.student_id.like(like), User.name.like(like)),
    ).order_by(User.student_id.asc()).limit(20).all()
    return ok([u.to_dict() for u in rows])


@bp.route("/set-role", methods=["POST"])
@super_required
def set_role():
    """设置用户角色（仅可在 admin / user 之间切换；超级管理员不可被修改）。"""
    data = request.get_json(silent=True) or {}
    student_id = (data.get("student_id") or "").strip()
    role = data.get("role")
    if role not in ("admin", "user"):
        return fail("无效的角色", code=1002)
    target = User.query.filter_by(student_id=student_id).first()
    if target is None:
        return fail("该学号尚未登录过本系统，无法设置", code=1002)
    if target.role == "superadmin":
        return fail("不能修改超级管理员的角色", code=1002)
    if target.id == g.user.id:
        return fail("不能修改自己的角色", code=1002)

    target.role = role
    log_action(g.user.id, "set_role", f"{target.student_id} → {role}")
    db.session.commit()
    return ok(target.to_dict(), msg=f"已{'设为管理员' if role == 'admin' else '移除管理员'}")
