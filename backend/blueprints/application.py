# -*- coding: utf-8 -*-
"""打印申请模块：提交（含文件/签名上传）、我的申请列表、申请详情。

对应 Word 表单「附件1 3D打印服务申请表单」，字段映射：
  申请人基本信息 -> 取自登录用户（自动填充）
  打印用途/材料/数量/STL文件/备注 -> 表单字段
  电子签名 -> canvas 生成的 base64，后端转 PNG 存储
"""
import os
import re
import base64
import uuid
from datetime import datetime

from flask import Blueprint, request, g, current_app, send_file
from extensions import db
from models import PrintApplication
from utils.response import ok, fail
from utils.auth import login_required
from services.quota import ensure_quota
from services.logger import log_action
from services.form_export import generate_application_docx

bp = Blueprint("application", __name__)

# 打印用途可选值（与前端单选项一致）
ALLOWED_PURPOSE = ["course", "research", "competition", "graduation", "club", "other"]

# 状态 -> 中文（供前端展示，也可由前端自行映射）
STATUS_SET = {"pending", "approved", "rejected", "printing", "completed", "cancelled"}


def _save_stl(file_storage):
    """校验并保存 STL 文件，返回落库用的相对 URL 路径（uploads/stl/...）。"""
    if file_storage is None or file_storage.filename == "":
        return None
    if not file_storage.filename.lower().endswith(".stl"):
        raise ValueError("模型文件仅支持 .stl 格式")

    data = file_storage.read()
    if len(data) == 0:
        raise ValueError("模型文件为空")
    if len(data) > current_app.config["MAX_STL_SIZE"]:
        raise ValueError("模型文件不能超过 50MB")

    sub = f"stl/{datetime.now().strftime('%Y%m')}/{uuid.uuid4().hex}.stl"
    abs_path = os.path.join(current_app.config["UPLOAD_DIR"], sub)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as f:
        f.write(data)
    return "uploads/" + sub  # 相对 URL，由 Nginx 的 /uploads/ 路径对外提供


def _save_sign(sign_b64):
    """把前端 canvas 生成的 base64 签名转存为 PNG，返回相对 URL 路径。"""
    if not sign_b64:
        return None
    if "," in sign_b64:  # 去掉 "data:image/png;base64," 前缀
        sign_b64 = sign_b64.split(",", 1)[1]
    try:
        data = base64.b64decode(sign_b64)
    except Exception:
        raise ValueError("签名数据格式错误")

    sub = f"sign/{datetime.now().strftime('%Y%m')}/{uuid.uuid4().hex}.png"
    abs_path = os.path.join(current_app.config["UPLOAD_DIR"], sub)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as f:
        f.write(data)
    return "uploads/" + sub


def _save_feedback_image(file_storage):
    """校验并保存反馈图片（实物图/现场照片），返回相对 URL 路径。"""
    if file_storage is None or file_storage.filename == "":
        raise ValueError("请上传反馈图片")
    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        raise ValueError("反馈图片仅支持 jpg/png 等图片格式")

    data = file_storage.read()
    if len(data) == 0:
        raise ValueError("反馈图片为空")
    if len(data) > 5 * 1024 * 1024:
        raise ValueError("反馈图片不能超过 5MB")

    sub = f"feedback/{datetime.now().strftime('%Y%m')}/{uuid.uuid4().hex}{ext}"
    abs_path = os.path.join(current_app.config["UPLOAD_DIR"], sub)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "wb") as f:
        f.write(data)
    return "uploads/" + sub


def _gen_apply_no():
    """生成申请编号，形如 HUST3D20260908001（当天三位流水）。"""
    prefix = "HUST3D" + datetime.now().strftime("%Y%m%d")
    count = db.session.query(PrintApplication).filter(
        PrintApplication.apply_no.like(prefix + "%")
    ).count()
    return f"{prefix}{count + 1:03d}"


@bp.route("/submit", methods=["POST"])
@login_required
def submit():
    """提交打印申请（multipart/form-data，含 STL 文件与签名 base64）。"""
    user = g.user

    # 配额校验：本学期剩余次数为 0 则直接拦截
    remaining = ensure_quota(user)
    if remaining <= 0:
        return fail("本学期剩余打印次数为 0，无法提交", code=1001)

    form = request.form
    purpose = form.get("purpose", "")
    if purpose not in ALLOWED_PURPOSE:
        return fail("请选择打印用途", code=1002)

    purpose_other = form.get("purpose_other", "").strip() if purpose == "other" else None
    if purpose == "other" and not purpose_other:
        return fail("请填写打印用途说明", code=1002)

    try:
        model_count = int(form.get("model_count", 1) or 1)
    except ValueError:
        model_count = 1
    if model_count < 1:
        model_count = 1

    material = form.get("material", "PLA") or "PLA"
    remark = form.get("remark", "").strip()

    # 联系方式 / 邮箱（必填，提交时同步更新到用户资料）
    phone = form.get("phone", "").strip()
    email = form.get("email", "").strip()
    if not phone:
        return fail("请填写联系方式", code=1002)
    if not re.fullmatch(r"1\d{10}", phone):
        return fail("联系方式格式不正确，请填写 11 位手机号", code=1002)
    if not email:
        return fail("请填写电子邮箱", code=1002)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return fail("电子邮箱格式不正确", code=1002)

    # 文件与签名（抛 ValueError 时转为业务错误）
    try:
        file_url = _save_stl(request.files.get("file"))
        sign_url = _save_sign(form.get("sign", ""))
    except ValueError as e:
        return fail(str(e), code=1002)

    # 生成编号并查重，撞号则重试
    apply_no = None
    for _ in range(5):
        candidate = _gen_apply_no()
        if db.session.query(PrintApplication).filter_by(apply_no=candidate).first() is None:
            apply_no = candidate
            break
    if apply_no is None:
        return fail("系统繁忙，请稍后重试", code=500, http_status=500)

    app_obj = PrintApplication(
        user_id=user.id,
        apply_no=apply_no,
        purpose=purpose,
        purpose_other=purpose_other,
        material=material,
        model_count=model_count,
        file_url=file_url,
        remark=remark,
        sign_url=sign_url,
        status="pending",
    )
    db.session.add(app_obj)

    # 配额扣减
    user.remaining_quota -= 1
    # 同步联系方式 / 邮箱
    user.phone = phone
    user.email = email
    log_action(user.id, "submit_application", f"提交申请 {apply_no}")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("提交失败，请重试", code=500, http_status=500)

    return ok(app_obj.to_dict(), msg="提交成功")


@bp.route("/list", methods=["GET"])
@login_required
def my_list():
    """获取我的申请列表，可按状态筛选。"""
    status = request.args.get("status", "")
    q = db.session.query(PrintApplication).filter_by(user_id=g.user.id)
    if status in STATUS_SET:
        q = q.filter_by(status=status)
    rows = q.order_by(PrintApplication.created_at.desc()).all()
    return ok([r.to_dict() for r in rows])


@bp.route("/detail/<int:app_id>", methods=["GET"])
@login_required
def detail(app_id):
    """获取申请详情（仅本人或管理员可见）。"""
    app_obj = db.session.get(PrintApplication, app_id)
    if app_obj is None:
        return fail("申请不存在", code=404, http_status=404)
    if app_obj.user_id != g.user.id and g.user.role != "admin":
        return fail("无权查看该申请", code=403, http_status=403)
    return ok(app_obj.to_dict())


@bp.route("/export/<int:app_id>", methods=["GET"])
@login_required
def export_word(app_id):
    """导出申请为 Word 文档（按「附件1 3D打印服务申请表单」官方版式，本人或管理员）。"""
    app_obj = db.session.get(PrintApplication, app_id)
    if app_obj is None:
        return fail("申请不存在", code=404, http_status=404)
    if app_obj.user_id != g.user.id and g.user.role != "admin":
        return fail("无权导出该申请", code=403, http_status=403)

    buf = generate_application_docx(app_obj, current_app.config["UPLOAD_DIR"])
    filename = f"3D打印服务申请表单-{app_obj.apply_no}.docx"
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@bp.route("/feedback/<int:app_id>", methods=["POST"])
@login_required
def feedback(app_id):
    """打印完成后提交反馈（上传实物图/现场照片），成功后奖励 1 次打印机会。"""
    user = g.user
    app_obj = db.session.get(PrintApplication, app_id)
    if app_obj is None:
        return fail("申请不存在", code=404, http_status=404)
    if app_obj.user_id != user.id:
        return fail("无权操作该申请", code=403, http_status=403)
    if app_obj.status != "completed":
        return fail("仅已完成的订单可提交反馈", code=1002)
    if app_obj.feedback_url:
        return fail("该订单已反馈，不可重复提交", code=1002)

    try:
        feedback_url = _save_feedback_image(request.files.get("file"))
    except ValueError as e:
        return fail(str(e), code=1002)

    app_obj.feedback_url = feedback_url
    app_obj.feedback_at = datetime.now()

    # 反馈成功奖励 1 次打印机会（先确保配额为当前学期值）
    ensure_quota(user)
    user.remaining_quota += 1

    log_action(user.id, "feedback", f"订单 {app_obj.apply_no} 提交反馈，奖励 1 次打印机会")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("反馈提交失败，请重试", code=500, http_status=500)

    return ok(app_obj.to_dict(), msg="反馈成功，已奖励 1 次打印机会")
