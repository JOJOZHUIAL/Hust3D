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
from services.notify import notify_admins, notify_user
from services.form_export import generate_application_docx, generate_batch_docx


def _safe_name(s):
    """去掉文件名非法字符（下载命名用）。"""
    return re.sub(r'[\/:*?"<>|]', "", s or "").strip()

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

    # 提醒全部管理员有新申请
    preview = f"{material} x{model_count} · {os.path.basename(file_url or '')}"
    notify_admins("apply", f"新打印申请 {apply_no}",
                  f"{user.name or user.student_id} 提交了打印申请：{preview}",
                  link="/admin/pending")
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
    if app_obj.user_id != g.user.id and g.user.role not in ("admin", "superadmin"):
        return fail("无权查看该申请", code=403, http_status=403)
    return ok(app_obj.to_dict())


@bp.route("/export/<int:app_id>", methods=["GET"])
@login_required
def export_word(app_id):
    """导出申请为 Word 文档（按「附件1 3D打印服务申请表单」官方版式，本人或管理员）。"""
    app_obj = db.session.get(PrintApplication, app_id)
    if app_obj is None:
        return fail("申请不存在", code=404, http_status=404)
    if app_obj.user_id != g.user.id and g.user.role not in ("admin", "superadmin"):
        return fail("无权导出该申请", code=403, http_status=403)

    buf = generate_application_docx(app_obj, current_app.config["UPLOAD_DIR"])
    owner_name = _safe_name(app_obj.user.name) if app_obj.user else ""
    filename = f"{owner_name}{app_obj.apply_no}.docx"
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@bp.route("/export-batch", methods=["GET"])
@login_required
def export_batch():
    """批量导出申请表：多份合并为一个 Word（每份申请一页），仅限本人申请。"""
    ids_raw = request.args.get("ids", "")
    id_list = []
    for part in ids_raw.split(","):
        part = part.strip()
        if part.isdigit():
            id_list.append(int(part))
    id_list = list(dict.fromkeys(id_list))[:100]  # 去重限 100 份
    if not id_list:
        return fail("请先筛选出要导出的申请", code=1002)

    apps = (
        PrintApplication.query.filter(
            PrintApplication.id.in_(id_list),
            PrintApplication.user_id == g.user.id,
        )
        .order_by(PrintApplication.created_at.asc())
        .all()
    )
    if not apps:
        return fail("没有可导出的申请", code=404, http_status=404)

    buf = generate_batch_docx(apps, current_app.config["UPLOAD_DIR"])
    filename = f"申请表_{len(apps)}份_{datetime.now().strftime('%Y%m%d')}.docx"
    log_action(g.user.id, "export_batch", f"批量导出 {len(apps)} 份申请表")
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@bp.route("/attachment/<int:app_id>", methods=["GET"])
@login_required
def attachment(app_id):
    """下载申请相关附件（type=model：STL 模型；type=feedback：反馈图片）。

    下载名统一为「姓名 + 申请编号 + 原扩展名」，不再暴露服务器随机文件名。
    """
    app_obj = db.session.get(PrintApplication, app_id)
    if app_obj is None:
        return fail("申请不存在", code=404, http_status=404)
    if app_obj.user_id != g.user.id and g.user.role not in ("admin", "superadmin"):
        return fail("无权下载该申请的附件", code=403, http_status=403)

    ftype = request.args.get("type", "model")
    rel = app_obj.file_url if ftype == "model" else app_obj.feedback_url if ftype == "feedback" else None
    if not rel:
        return fail("附件不存在", code=404, http_status=404)

    abs_path = os.path.join(current_app.config["UPLOAD_DIR"], rel.split("uploads/", 1)[-1])
    if not os.path.isfile(abs_path):
        return fail("附件文件已丢失", code=404, http_status=404)

    owner_name = _safe_name(app_obj.user.name) if app_obj.user else ""
    ext = os.path.splitext(rel)[1] or ".bin"
    download = f"{owner_name}{app_obj.apply_no}{ext}"
    return send_file(abs_path, as_attachment=True, download_name=download)


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

    # 奖励模式由 FEEDBACK_REWARD_MODE 决定：auto=自动+1；review=管理员审核后 +1
    if current_app.config.get("FEEDBACK_REWARD_MODE") == "review":
        app_obj.feedback_reviewed = False
        notify_admins("feedback", f"新反馈待审核 {app_obj.apply_no}",
                      f"{user.name or user.student_id} 上传了实物图，请在审核后发放奖励",
                      link="/admin/pending")
        msg = "反馈已提交，等待管理员审核"
        log_action(user.id, "feedback", f"订单 {app_obj.apply_no} 提交反馈（待审核）")
    else:
        app_obj.feedback_reviewed = True
        ensure_quota(user)
        user.remaining_quota += 1
        msg = "反馈成功，已奖励 1 次打印机会"
        log_action(user.id, "feedback", f"订单 {app_obj.apply_no} 提交反馈，自动奖励 1 次打印机会")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("反馈提交失败，请重试", code=500, http_status=500)

    return ok(app_obj.to_dict(), msg=msg)
