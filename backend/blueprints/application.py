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
from models import ChatMessage, FeedbackImage, PrintApplication, feedback_expire_days
from utils.response import ok, fail
from utils.auth import login_required
from services.quota import ensure_quota
from services.logger import log_action
from services.notify import notify_admins, notify_user
from services.expiry import expire_stale_silently
from services.form_export import generate_application_docx


def _safe_name(s):
    """去掉文件名非法字符（下载命名用）。"""
    return re.sub(r'[\/:*?"<>|]', "", s or "").strip()


def _remove_upload_files(urls):
    """删除 uploads 下的物理文件（撤回申请时清理 STL / 签名图，失败不影响主流程）。"""
    for rel in urls:
        if not rel:
            continue
        try:
            abs_path = os.path.join(current_app.config["UPLOAD_DIR"], rel.split("uploads/", 1)[-1])
            if os.path.isfile(abs_path):
                os.remove(abs_path)
        except OSError:
            current_app.logger.warning("删除附件失败：%s", rel)


bp = Blueprint("application", __name__)

# 打印用途可选值（与前端单选项一致）
ALLOWED_PURPOSE = ["course", "research", "competition", "graduation", "club", "other"]

# 状态 -> 中文（供前端展示，也可由前端自行映射）
# 注意：过期不是独立状态 —— 状态仍是 completed，用 expired_at 标记
STATUS_SET = {"pending", "approved", "rejected", "printing", "completed", "cancelled"}


def _save_stl(file_storage):
    """校验并保存 STL 文件，返回 (落库用相对 URL, 原始文件名)（uploads/stl/...）。"""
    if file_storage is None or file_storage.filename == "":
        return None, None
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
    # 原始文件名仅用于展示（如打印机状态页「正在打印 xxx.stl」），落盘名保持随机
    original = os.path.basename(file_storage.filename.replace("\\", "/"))[:255]
    return "uploads/" + sub, original  # 相对 URL，由 Nginx 的 /uploads/ 路径对外提供


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

    # 预计反馈时间（选填，YYYY-MM-DD）：学生自己声明的计划反馈日期
    # 只要填了（即不按默认期限），就必须说明原因
    expected_raw = (form.get("expected_feedback_at") or "").strip()
    expected_note = (form.get("expected_feedback_note") or "").strip()
    expected_feedback_at = None
    if expected_raw:
        try:
            expected_feedback_at = datetime.strptime(expected_raw[:10], "%Y-%m-%d")
        except ValueError:
            return fail("预计反馈时间格式不正确", code=1002)
        if expected_feedback_at.date() < datetime.now().date():
            return fail("预计反馈时间不能早于今天", code=1002)
        if not expected_note:
            return fail("不按默认期限反馈时，请说明情况（例如比赛/课程安排）", code=1002)
        if len(expected_note) > 200:
            return fail("情况说明过长（最多 200 字）", code=1002)
    else:
        expected_note = None

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
        file_url, file_name = _save_stl(request.files.get("file"))
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
        file_name=file_name,
        remark=remark,
        sign_url=sign_url,
        expected_feedback_at=expected_feedback_at,
        expected_feedback_note=expected_note,
        status="pending",
    )
    db.session.add(app_obj)

    # 配额扣减
    user.remaining_quota -= 1
    # 同步联系方式 / 邮箱
    user.phone = phone
    user.email = email

    # 提醒全部管理员有新申请
    preview = f"{material} x{model_count} · {file_name or ''}"
    notify_admins("apply", f"新打印申请 {apply_no}",
                  f"{user.name or user.student_id} 提交了打印申请：{preview}",
                  link="/admin/pending?cat=pending")
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
    expire_stale_silently()  # 先做过期扫描，保证「未反馈」不会一直挂着
    status = request.args.get("status", "")
    q = db.session.query(PrintApplication).filter_by(user_id=g.user.id)
    if status == "expired":  # 伪状态：已完成且反馈超时
        q = q.filter(PrintApplication.expired_at.isnot(None))
    elif status in STATUS_SET:
        q = q.filter_by(status=status)
    rows = q.order_by(PrintApplication.created_at.desc()).all()
    return ok([r.to_dict() for r in rows])


@bp.route("/detail/<int:app_id>", methods=["GET"])
@login_required
def detail(app_id):
    """获取申请详情（仅本人或管理员可见）。"""
    expire_stale_silently()
    app_obj = db.session.get(PrintApplication, app_id)
    if app_obj is None:
        return fail("申请不存在", code=404, http_status=404)
    if app_obj.user_id != g.user.id and g.user.role not in ("admin", "superadmin"):
        return fail("无权查看该申请", code=403, http_status=403)
    return ok(app_obj.to_dict())


@bp.route("/withdraw/<int:app_id>", methods=["POST"])
@login_required
def withdraw(app_id):
    """撤回申请：仅限待审批状态。

    提交后发现有误可撤回：直接删除申请记录与已上传的 STL / 签名文件，
    并把提交时扣减的 1 次打印机会返还（即撤回不消耗打印次数）。
    """
    app_obj = db.session.get(PrintApplication, app_id)
    if app_obj is None:
        return fail("申请不存在", code=404, http_status=404)
    if app_obj.user_id != g.user.id:
        return fail("无权操作该申请", code=403, http_status=403)
    if app_obj.status != "pending":
        return fail("仅待审批的申请可以撤回，已进入审批流程请联系管理员", code=1002)

    apply_no = app_obj.apply_no
    file_urls = [app_obj.file_url, app_obj.sign_url]
    db.session.delete(app_obj)

    # 返还提交时扣掉的 1 次（撤回不消耗打印次数）
    user = g.user
    ensure_quota(user)
    user.remaining_quota += 1
    log_action(user.id, "withdraw_application",
               f"撤回并删除申请 {apply_no}，返还 1 次打印机会")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("撤回失败，请重试", code=500, http_status=500)

    _remove_upload_files(file_urls)
    return ok({"apply_no": apply_no, "remaining_quota": user.remaining_quota},
              msg="申请已撤回删除，打印次数已返还")


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


def _dt_text(dt):
    """时间格式化成前端直接展示的字符串。"""
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


@bp.route("/todos", methods=["GET"])
@login_required
def todos():
    """首页「待办任务」清单（统一接口，按角色返回）。

    学生：待取件 + 待反馈的逐条清单（已完成的申请，还差动作）；
    管理员：汇总待办（待审批申请 / 待回复留言 / 待审核反馈），前端点击进入对应管理页。
    """
    # —— 管理员：汇总待办 ——
    if g.user.role in ("admin", "superadmin"):
        pending = PrintApplication.query.filter_by(status="pending").count()
        approved = PrintApplication.query.filter_by(status="approved").count()
        feedback = PrintApplication.query.filter(
            PrintApplication.feedback_url.isnot(None),
            PrintApplication.feedback_reviewed == 0,
        ).count()
        chat = ChatMessage.query.filter_by(sender_role="user", is_read=False).count()
        items = [
            {"kind": "approve", "label": "待审批申请", "count": pending,
             "link": "/admin/pending", "cat": "pending"},
            {"kind": "print", "label": "待打印", "count": approved,
             "link": "/admin/pending", "cat": "approved"},
            {"kind": "chat", "label": "待回复留言", "count": chat, "link": "/admin/chat"},
            {"kind": "feedback_review", "label": "待审核反馈", "count": feedback,
             "link": "/admin/pending", "cat": "fedback"},
        ]
        return ok({
            "count": sum(i["count"] for i in items),
            "items": items,
        })

    # —— 学生：待取件 + 待反馈 ——
    expire_stale_silently()
    rows = (
        db.session.query(PrintApplication)
        .filter(
            PrintApplication.user_id == g.user.id,
            PrintApplication.status == "completed",
        )
        .order_by(PrintApplication.completed_at.asc(), PrintApplication.id.asc())
        .all()
    )

    pickups, feedbacks = [], []
    for r in rows:
        base = {
            "id": r.id,
            "apply_no": r.apply_no,
            "file_name": r.file_name,
            "completed_at": _dt_text(r.completed_at),
            "feedback_deadline": _dt_text(r.feedback_deadline()),
            "expired": r.expired_at is not None,
            "status": r.status,
        }
        if not r.picked_up:
            pickups.append({**base, "kind": "pickup"})
        # 未反馈的都列出来（过期的也能补交反馈，标记 expired 供前端提示）
        if not r.feedback_url:
            feedbacks.append({**base, "kind": "feedback"})

    items = pickups + feedbacks
    return ok({
        "count": len(items),
        "pickup_count": len(pickups),
        "feedback_count": len(feedbacks),
        "items": items,
    })


@bp.route("/pickup/<int:app_id>", methods=["POST"])
@login_required
def mark_picked_up(app_id):
    """学生自助标记「已领取」。

    置 picked_up / pick_up_date 后，首页「待取件」与取件提醒弹窗都会自然消失
    （弹窗数据本身就是按「已完成且未领取」筛的）。
    """
    app_obj = db.session.get(PrintApplication, app_id)
    if app_obj is None:
        return fail("申请不存在", code=404, http_status=404)
    if app_obj.user_id != g.user.id:
        return fail("无权操作该申请", code=403, http_status=403)
    if app_obj.status != "completed":
        return fail("仅已完成的申请可以标记领取", code=1002)
    if app_obj.picked_up:
        return ok(app_obj.to_dict(), msg="该申请已是已领取状态")

    app_obj.picked_up = True
    app_obj.pick_up_date = datetime.now()
    log_action(g.user.id, "pick_up", f"标记已领取 {app_obj.apply_no}")
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("操作失败，请重试", code=500, http_status=500)
    return ok(app_obj.to_dict(), msg="已标记为已领取")


@bp.route("/meta", methods=["GET"])
@login_required
def meta():
    """申请表单需要的配置（反馈期限天数等）。"""
    return ok({
        "feedback_expire_days": feedback_expire_days(),
        "feedback_reward_mode": current_app.config.get("FEEDBACK_REWARD_MODE") or "review",
        "reward_expired": bool(current_app.config.get("FEEDBACK_REWARD_EXPIRED")),
        "default_quota": current_app.config.get("DEFAULT_QUOTA"),
    })


@bp.route("/feedback/<int:app_id>", methods=["POST"])
@login_required
def feedback(app_id):
    """提交/追加反馈图片（可多张、可重复上传）。

    规则：
    - 已完成的订单都能上传，**过期也可以补交**；
    - 过期后的反馈**仍需管理员审核**（是否给奖励由 FEEDBACK_REWARD_EXPIRED 决定）；
    - 不满意可以再次上传，图片累加不覆盖；
    - 奖励每单只发一次（feedback_rewarded 保证不会重复加次数）。
    """
    user = g.user
    expire_stale_silently()
    app_obj = db.session.get(PrintApplication, app_id)
    if app_obj is None:
        return fail("申请不存在", code=404, http_status=404)
    if app_obj.user_id != user.id:
        return fail("无权操作该申请", code=403, http_status=403)
    if app_obj.status != "completed":
        return fail("仅已完成的订单可提交反馈", code=1002)

    # 支持一次选多张：字段名 file / files 都认
    uploads = list(request.files.getlist("file")) + list(request.files.getlist("files"))
    uploads = [f for f in uploads if f is not None and f.filename]
    if not uploads:
        return fail("请上传反馈图片", code=1002)
    if len(uploads) > 9:
        return fail("一次最多上传 9 张图片", code=1002)

    saved = []
    try:
        for f in uploads:
            saved.append(_save_feedback_image(f))
    except ValueError as e:
        return fail(str(e), code=1002)

    first_time = app_obj.feedback_url is None
    if first_time:
        app_obj.feedback_url = saved[0]  # 第一张作封面（列表/下载用）
    app_obj.feedback_at = datetime.now()
    for rel in saved:
        db.session.add(FeedbackImage(application_id=app_obj.id, url=rel, uploader_id=user.id))

    # 上传反馈即视为已取件（学生在工作室现场拍摄上传）
    if not app_obj.picked_up:
        app_obj.picked_up = True
        app_obj.pick_up_date = datetime.now()

    expired = app_obj.expired_at is not None
    reward_mode = current_app.config.get("FEEDBACK_REWARD_MODE") or "review"
    reward_expired = current_app.config.get("FEEDBACK_REWARD_EXPIRED", True)
    already_rewarded = bool(app_obj.feedback_rewarded)

    if already_rewarded:
        # 追加图片：审核状态和奖励都不变
        msg = f"已追加 {len(saved)} 张反馈图片"
    elif expired:
        # 过期补交：仍然需要管理员审核，但审核通过也不发奖励
        app_obj.feedback_reviewed = False
        notify_admins("feedback", f"过期补交反馈待审核 {app_obj.apply_no}",
                      f"{user.name or user.student_id} 补交了 {len(saved)} 张实物图"
                      f"（该申请已过期，通过后不发放奖励）",
                      link=f"/application/{app_obj.id}")
        msg = "反馈已补交，等待管理员审核（该申请已过期，不发放奖励）"
    elif reward_mode == "review":
        app_obj.feedback_reviewed = False
        notify_admins("feedback", f"新反馈待审核 {app_obj.apply_no}",
                      f"{user.name or user.student_id} 上传了 {len(saved)} 张实物图，请在审核后发放奖励",
                      link=f"/application/{app_obj.id}")
        msg = "反馈已提交，等待管理员审核"
    else:
        app_obj.feedback_reviewed = True
        ensure_quota(user)
        user.remaining_quota += 1
        app_obj.feedback_rewarded = True
        msg = "反馈成功，已奖励 1 次打印机会"

    log_action(user.id, "feedback",
               f"订单 {app_obj.apply_no} 上传 {len(saved)} 张反馈图"
               + ("（已过期，待管理员审核）" if expired and not already_rewarded else ""))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return fail("反馈提交失败，请重试", code=500, http_status=500)

    return ok(app_obj.to_dict(), msg=msg)
