# -*- coding: utf-8 -*-
"""管理员端：待审批列表、审批（通过/拒绝）、打印状态更新、批量导出申请表。"""
import io
from datetime import datetime, timedelta

from flask import Blueprint, current_app, request, g, send_file
from sqlalchemy import or_
from extensions import db
from models import PrintApplication, Printer, User, SmsMessage, FeedbackImage, feedback_expire_days
from utils.response import ok, fail
from utils.auth import admin_required, super_required, resolve_operator
from utils.env_file import update_list_var
from services.quota import ensure_quota
from services.logger import log_action
from services.mailer import send_mail_async
from services.quota import ensure_quota
from services.notify import notify_user, notify_pickup
from services import sms
from services.expiry import expire_stale_silently
from services.form_export import build_applications_zip

bp = Blueprint("admin", __name__)

# 管理员可筛选的状态（与前端 chips 对应；expired 是伪状态 = 已完成且反馈超时）
FILTER_STATUS = {"pending", "approved", "rejected", "printing", "completed", "cancelled"}

# 一次批量导出最多多少份（防止选了超大区间把内存打爆）
MAX_EXPORT = 300


def _parse_day(raw, end_of_day=False):
    """把 YYYY-MM-DD 解析成当天 00:00:00 / 23:59:59；非法返回 None。"""
    if not raw:
        return None
    try:
        d = datetime.strptime(raw, "%Y-%m-%d")
    except ValueError:
        return None
    return d.replace(hour=23, minute=59, second=59, microsecond=0) if end_of_day else d


@bp.route("/applications/export", methods=["GET"])
@admin_required
def export_applications():
    """按时间范围批量导出申请表（管理员）。

    返回 ZIP，里面每个申请一个独立的 Word 文件（姓名+申请编号.docx）。
    查询参数：start / end（YYYY-MM-DD，按提交时间筛选，可只传一端）、status（可选）。
    """
    start_raw = (request.args.get("start") or "").strip()
    end_raw = (request.args.get("end") or "").strip()
    status = (request.args.get("status") or "").strip()

    start = _parse_day(start_raw)
    end = _parse_day(end_raw, end_of_day=True)
    if start_raw and start is None:
        return fail("开始日期格式应为 YYYY-MM-DD", code=1002)
    if end_raw and end is None:
        return fail("结束日期格式应为 YYYY-MM-DD", code=1002)
    if start and end and start > end:
        return fail("开始日期不能晚于结束日期", code=1002)

    q = db.session.query(PrintApplication)
    if start is not None:
        q = q.filter(PrintApplication.created_at >= start)
    if end is not None:
        q = q.filter(PrintApplication.created_at <= end)
    if status in FILTER_STATUS:
        q = q.filter_by(status=status)
    rows = q.order_by(PrintApplication.created_at.asc()).limit(MAX_EXPORT).all()

    if not rows:
        return fail("该时间范围内没有申请可导出", code=404, http_status=404)

    buf = build_applications_zip(rows, current_app.config["UPLOAD_DIR"])
    label = f"{start_raw or '最早'}_{end_raw or '最新'}"
    filename = f"申请表_{label}_{len(rows)}份.zip"
    log_action(g.user.id, "export_applications",
               f"批量导出申请表 {len(rows)} 份（{start_raw or '最早'} ~ {end_raw or '最新'}）")
    db.session.commit()
    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/zip",
    )


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
    expire_stale_silently()  # 先做过期扫描，保证「未反馈」的池子是干净的
    status = request.args.get("status", "")
    q = db.session.query(PrintApplication)
    if status == "expired":  # 伪状态：已完成且反馈超时
        q = q.filter(PrintApplication.expired_at.isnot(None))
    elif status in FILTER_STATUS:
        q = q.filter_by(status=status)
    rows = q.order_by(PrintApplication.created_at.desc()).all()
    return ok([r.to_dict() for r in rows])


@bp.route("/application/review", methods=["POST"])
@admin_required
def review():
    """审批操作：通过 / 拒绝（拒绝必须填原因，且不消耗学生的打印次数）。"""
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

    # 公共管理员账号：必须登记实际操作人
    operator, err = resolve_operator(data)
    if err:
        return err

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
        # 打印被拒绝不消耗打印次数：把提交时扣减的 1 次返还给学生
        ensure_quota(app_obj.user)
        app_obj.user.remaining_quota += 1
        notify_user(app_obj.user_id, "approval",
                    f"申请 {app_obj.apply_no} 未通过",
                    f"{comment}（本次不消耗打印次数）",
                    link=f"/application/{app_obj.id}")
    else:
        return fail("无效的审批操作", code=1002)

    # 记录审批人信息（id + 姓名/学号快照），便于事后追溯
    app_obj.reviewer_id = operator.id
    app_obj.reviewer_name = operator.name
    app_obj.reviewer_student_id = operator.student_id
    app_obj.reviewer_sign = reviewer_sign or None
    app_obj.reviewed_at = datetime.now()
    extra = "，已返还 1 次打印机会" if action == "reject" else ""
    if getattr(g.user, "is_shared_admin", False):
        extra += f"（公共账号操作，操作人：{operator.name}）"
    log_action(operator.id, "review",
               f"{action} 申请 {app_obj.apply_no}: {comment}{extra}")
    db.session.commit()
    return ok(app_obj.to_dict(), msg="操作成功")


@bp.route("/application/status", methods=["PUT"])
@admin_required
def update_status():
    """手动推进打印状态：已通过 → 打印中（绑定打印机）→ 已完成（可标记领取）。"""
    data = request.get_json(silent=True) or {}
    app_id = data.get("id")
    status = data.get("status")
    picked_up = bool(data.get("picked_up", False))
    printer_id = data.get("printer_id")
    reason = (data.get("reason") or "").strip()

    if status not in {"printing", "completed", "cancelled", "failed"}:
        return fail("无效的状态", code=1002)

    app_obj = db.session.get(PrintApplication, app_id)
    if app_obj is None:
        return fail("申请不存在", code=404, http_status=404)

    # —— 打印失败：原因必填，返还 1 次打印次数，站内 + 邮件通知学生 ——
    if status == "failed":
        if app_obj.status not in ("approved", "printing"):
            return fail("仅「已通过」或「打印中」的申请可标记打印失败", code=1002)
        if not reason:
            return fail("请填写打印失败原因", code=1002)
        # 公共管理员账号：标记打印失败也要登记实际操作人
        operator, err = resolve_operator(data)
        if err:
            return err
        app_obj.status = "failed"
        app_obj.admin_comment = reason
        user = app_obj.user
        ensure_quota(user)
        user.remaining_quota += 1
        notify_user(user.id, "status", f"申请 {app_obj.apply_no} 打印失败",
                    f"原因：{reason}。打印次数已返还，可修改模型后重新提交。",
                    link=f"/application/{app_obj.id}")
        if user.email:
            send_mail_async(
                user.email,
                f"【3D打印服务】申请 {app_obj.apply_no} 打印失败",
                f"{user.name or ''} 同学：\n\n"
                f"你提交的申请（{app_obj.apply_no}）因以下原因无法成功打印：\n"
                f"{reason}\n\n"
                f"本次打印次数已返还至你的账户，欢迎修改模型后重新提交。\n\n"
                f"理工智造共享平台 · 大学生创新创业协会",
            )
        log_action(operator.id, "update_status",
                   f"申请 {app_obj.apply_no} 标记打印失败，返还次数"
                   + (f"（公共账号操作，操作人：{operator.name}）"
                      if getattr(g.user, "is_shared_admin", False) else ""))
        db.session.commit()
        return ok(app_obj.to_dict(), msg="已标记打印失败，打印次数已返还")

    send_sms_after_commit = False
    app_obj.status = status
    # 公共管理员账号点「开始打印」时必须登记实际操作人
    operator, err = resolve_operator(data, required=(status == "printing"))
    if err:
        return err
    if status == "printing":
        # —— 绑定打印机：让打印机状态页显示「正在打印该申请的 STL」，并开启进度自动完成 ——
        printer = None
        if printer_id:
            try:
                printer = db.session.get(Printer, int(printer_id))
            except (TypeError, ValueError):
                printer = None
            if printer is None:
                return fail("打印机不存在", code=1002)
            # 同一台打印机允许多个申请（一盘多件时会一起打印）：
            # 是否真的在打某一单，由监视器按打印机上报的文件名判定，这里不再拦。

        app_obj.printer_id = printer.id if printer else None
        app_obj.printer_name = printer.name if printer else None
        app_obj.print_state = None
        app_obj.print_progress = 0 if printer else None
        app_obj.print_actual_file = None
        app_obj.print_matched = False
        app_obj.print_seen_running = False  # 等监视器确认打印机真的在打本申请
        app_obj.completed_auto = False
        app_obj.printed_at = datetime.now()
        # 记录打印人信息（id + 姓名/学号快照）；公共账号则记实际操作人
        app_obj.printed_by_id = operator.id
        app_obj.printed_by_name = operator.name
        app_obj.printed_by_student_id = operator.student_id
        notify_user(app_obj.user_id, "status",
                    f"申请 {app_obj.apply_no} 已安排打印",
                    (f"已安排到打印机「{printer.name}」打印「{app_obj.file_name or '模型文件'}」"
                     if printer else f"已安排打印「{app_obj.file_name or '模型文件'}」")
                    + "，打印完成后会通知你领取",
                    link=f"/application/{app_obj.id}")
    elif status == "completed":
        app_obj.completed_at = datetime.now()
        app_obj.completed_auto = False  # 人工标记
        # 不论是否打印机 100% 触发，都统一落成"打印完成"状态
        app_obj.print_state = "FINISH"
        app_obj.print_progress = 100
        if picked_up:
            app_obj.picked_up = True
            app_obj.pick_up_date = datetime.now()
            notify_user(app_obj.user_id, "status",
                        f"申请 {app_obj.apply_no} 已完成并领取",
                        f"感谢使用，欢迎在 {feedback_expire_days()} 天内上传实物图反馈，"
                        f"奖励 1 次打印机会",
                        link=f"/application/{app_obj.id}")
        else:
            # 未领取 → 发取件提醒，学生下次打开首页会弹窗提示取件
            notify_pickup(app_obj, f"取件后可在 {feedback_expire_days()} 天内上传实物图/现场照片反馈，"
                                   f"奖励 1 次打印机会")
            send_sms_after_commit = True

        # 打印完成：邮件通知领取（学生填过邮箱才发；SMTP 未配置则静默跳过）
        user = app_obj.user
        if user and user.email:
            from services import notify_templates
            _subj, _body = notify_templates.render_pickup_email(app_obj)
            send_mail_async(user.email, _subj, _body)
    log_action(g.user.id, "update_status",
               f"申请 {app_obj.apply_no} → {status}"
               + (f"（打印机：{app_obj.printer_name}）" if status == "printing" and app_obj.printer_name else ""))
    db.session.commit()

    # 提交后再发取件短信（入库 + 后台线程发送，连不上网关就留在队列里等重试）
    if send_sms_after_commit:
        try:
            sms.notify_pickup_sms(app_obj)
        except Exception:
            current_app.logger.warning("取件短信发送失败", exc_info=True)

    return ok(app_obj.to_dict(), msg="状态已更新")


@bp.route("/application/send-sms/<int:app_id>", methods=["POST"])
@admin_required
def resend_sms(app_id):
    """手动（重新）发送取件短信给申请人。"""
    app_obj = db.session.get(PrintApplication, app_id)
    if app_obj is None:
        return fail("申请不存在", code=404, http_status=404)
    if app_obj.status != "completed":
        return fail("仅已完成的申请可发送取件短信", code=1002)
    phone = ((app_obj.user.phone if app_obj.user else "") or "").strip()
    if not phone:
        return fail("申请人没有填写手机号", code=1002)

    msg_id = sms.notify_pickup_sms(app_obj, force=True, sync=True)
    if msg_id is None:
        return fail("短信未发送（请检查短信开关与网关配置）", code=1002)
    row = db.session.get(SmsMessage, msg_id)
    if row is not None and row.status == "sent":
        return ok(app_obj.to_dict(), msg=f"已发送到 {phone}")
    if row is not None and row.status == "pending":
        return ok(app_obj.to_dict(), msg="网关暂时连不上，已加入待发送队列，手机上线后自动补发")
    return fail((row.last_error if row else "") or "发送失败", code=1002)


@bp.route("/application/remind-feedback/<int:app_id>", methods=["POST"])
@admin_required
def remind_feedback(app_id):
    """给未反馈 / 已过期的申请人发反馈提醒短信（审批管理与详情页的按钮）。"""
    app_obj = db.session.get(PrintApplication, app_id)
    if app_obj is None:
        return fail("申请不存在", code=404, http_status=404)
    if app_obj.status != "completed":
        return fail("仅已完成的申请可提醒反馈", code=1002)
    if app_obj.feedback_url:
        return fail("该申请已提交反馈，无需提醒", code=1002)
    phone = ((app_obj.user.phone if app_obj.user else "") or "").strip()
    if not phone:
        return fail("申请人没有填写手机号", code=1002)
    if not current_app.config.get("SMS_ENABLED"):
        return fail("短信通知未启用（SMS_ENABLED=0）", code=1002)

    content = sms.build_feedback_remind_message(app_obj, expired=app_obj.expired_at is not None)
    msg, sent, detail = sms.send_or_queue(
        phone, content, kind="feedback_remind",
        application_id=app_obj.id, apply_no=app_obj.apply_no,
        receiver_name=app_obj.user.name if app_obj.user else None,
        sender_id=g.user.id, sender_name=g.user.name,
    )
    log_action(g.user.id, "remind_feedback_sms",
               f"反馈提醒短信 → {phone}（#{msg.id}，申请 {app_obj.apply_no}）")
    data = {"sms_id": msg.id, "phone": phone, "content": content,
            "status": msg.status, "queued": msg.status == "pending"}
    if sent:
        return ok(data, msg=f"已发送到 {phone}")
    if msg.status == "pending":
        return ok(data, msg="网关暂时连不上，已加入待发送队列，设备上线后自动补发")
    return fail(detail or "发送失败", code=1002)


@bp.route("/application/remind-feedback-email/<int:app_id>", methods=["POST"])
@admin_required
def remind_feedback_email(app_id):
    """给未反馈 / 已过期的申请人发反馈提醒邮件（与短信提醒并列的按钮）。"""
    from models import EmailMessage
    from services import notify_templates
    from services.mailer import send_mail_now

    app_obj = db.session.get(PrintApplication, app_id)
    if app_obj is None:
        return fail("申请不存在", code=404, http_status=404)
    if app_obj.status != "completed":
        return fail("仅已完成的申请可提醒反馈", code=1002)
    if app_obj.feedback_url:
        return fail("该申请已提交反馈，无需提醒", code=1002)

    to = ((app_obj.user.email if app_obj.user else "") or "").strip()
    if not to:
        return fail("申请人没有填写电子邮箱", code=1002)
    if not current_app.config.get("SMTP_HOST"):
        return fail("邮件通知未配置（.env 缺少 SMTP_HOST）", code=1002)

    expired = app_obj.expired_at is not None
    subject, body = notify_templates.render_remind_email(app_obj, expired=expired)
    row = EmailMessage(to_addr=to, subject=subject[:255], body=body[:10000])
    db.session.add(row)
    ok_flag, err = send_mail_now(to, subject, body)
    row.status = "sent" if ok_flag else "failed"
    row.error = None if ok_flag else (err or "")[:500]
    log_action(g.user.id, "remind_feedback_email",
               f"反馈提醒邮件 -> {to}（申请 {app_obj.apply_no}，{'已过期' if expired else '未过期'}）")
    db.session.commit()
    if not ok_flag:
        return fail(f"发送失败：{err}", code=1002)
    return ok({"to": to, "subject": subject, "body": body}, msg=f"已发送到 {to}")


@bp.route("/sms/send", methods=["POST"])
@admin_required
def sms_send_custom():
    """管理员自定义发短信到指定手机号。"""
    data = request.get_json(silent=True) or {}
    phone = (data.get("phone") or "").strip()
    content = (data.get("content") or "").strip()
    if not sms.PHONE_RE.match(phone):
        return fail("手机号格式不正确（11 位手机号）", code=1002)
    if not content:
        return fail("请填写短信内容", code=1002)
    if len(content) > 500:
        return fail("短信内容过长（最多 500 字）", code=1002)

    msg, sent, detail = sms.send_custom(phone, content, g.user)
    payload = msg.to_dict()
    if sent:
        return ok(payload, msg="已发送")
    if msg.status == "pending":
        return ok(payload, msg="网关暂时连不上，已加入待发送队列，手机上线后自动补发")
    return fail(detail, code=1002, data=payload)


@bp.route("/sms/messages", methods=["GET"])
@admin_required
def sms_messages():
    """短信记录（含待发送队列）。支持 ?status=sent|pending|failed 过滤与分页。"""
    status = (request.args.get("status") or "").strip()
    page = max(1, int(request.args.get("page") or 1))
    size = min(100, max(1, int(request.args.get("size") or 20)))

    q = SmsMessage.query
    if status in {"sent", "pending", "failed"}:
        q = q.filter_by(status=status)
    total = q.count()
    rows = (q.order_by(SmsMessage.id.desc())
             .offset((page - 1) * size).limit(size).all())
    counts = {
        "all": SmsMessage.query.count(),
        "sent": SmsMessage.query.filter_by(status="sent").count(),
        "pending": SmsMessage.query.filter_by(status="pending").count(),
        "failed": SmsMessage.query.filter_by(status="failed").count(),
    }
    return ok({
        "items": [r.to_dict() for r in rows],
        "total": total,
        "page": page,
        "size": size,
        "counts": counts,
    })


@bp.route("/sms/messages/<int:msg_id>/retry", methods=["POST"])
@admin_required
def sms_retry(msg_id):
    """手动重发一条（失败的或被卡住的）。"""
    row = db.session.get(SmsMessage, msg_id)
    if row is None:
        return fail("短信记录不存在", code=404, http_status=404)
    if row.status == "sent":
        return fail("该短信已发送成功，无需重发", code=1002)
    row.status = "pending"  # 允许手动重试失败记录
    db.session.commit()
    sent, detail = sms.try_send(msg_id)
    db.session.refresh(row)
    if sent:
        return ok(row.to_dict(), msg="已发送")
    if row.status == "pending":
        return ok(row.to_dict(), msg="网关暂时连不上，已加入待发送队列")
    return fail(detail, code=1002, data=row.to_dict())


@bp.route("/sms/messages/<int:msg_id>", methods=["DELETE"])
@admin_required
def sms_delete(msg_id):
    """删除一条短信记录（队列里的也会一起删掉）。"""
    row = db.session.get(SmsMessage, msg_id)
    if row is None:
        return fail("短信记录不存在", code=404, http_status=404)
    db.session.delete(row)
    db.session.commit()
    return ok(msg="已删除")


@bp.route("/sms/test", methods=["POST"])
@admin_required
def sms_test():
    """测试短信网关：给指定手机号发一条测试短信。"""
    data = request.get_json(silent=True) or {}
    phone = (data.get("phone") or "").strip()
    if not phone:
        return fail("请填写接收测试短信的手机号", code=1002)
    sent, detail = sms.test_gateway(phone)
    if sent:
        return ok({"detail": detail}, msg="测试短信已发送")
    return fail(detail, code=1002)


@bp.route("/sms/gateways", methods=["GET"])
@admin_required
def sms_gateways_list():
    """短信监听窗口列表（含每个窗口是否可达）。"""
    items = sms.probe_gateway() if current_app.config.get("SMS_ENABLED") else [
        {"url": u, "reachable": None} for u in sms.gateway_list()
    ]
    return ok({"items": items})


@bp.route("/sms/gateways", methods=["POST"])
@admin_required
def sms_gateways_add():
    """新增一个短信监听窗口（直接写回 .env，立即生效）。"""
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return fail("请填写监听窗口地址", code=1002)
    urls, err = sms.add_gateway(url)
    if err:
        return fail(err, code=1002)
    log_action(g.user.id, "sms_gateway_add", f"新增短信监听窗口 {url}")
    return ok({"items": urls}, msg="已添加")


@bp.route("/sms/gateways", methods=["DELETE"])
@admin_required
def sms_gateways_delete():
    """删除一个短信监听窗口（直接写回 .env，立即生效）。"""
    url = (request.args.get("url") or "").strip()
    if not url:
        data = request.get_json(silent=True) or {}
        url = (data.get("url") or "").strip()
    if not url:
        return fail("请指定要删除的监听窗口", code=1002)
    urls, err = sms.remove_gateway(url)
    if err:
        return fail(err, code=1002)
    log_action(g.user.id, "sms_gateway_del", f"删除短信监听窗口 {url}")
    return ok({"items": urls}, msg="已删除")


@bp.route("/sms/status", methods=["GET"])
@admin_required
def sms_status():
    """网关状态：是否启用、各监听窗口是否可达、待发送条数。"""
    cfg = current_app.config
    gateways = []
    if cfg.get("SMS_ENABLED"):
        gateways = sms.probe_gateway()
    return ok({
        "enabled": bool(cfg.get("SMS_ENABLED")),
        "gateway": cfg.get("SMS_GATEWAY_URL") or "",
        "gateways": gateways,
        "reachable": any(g["reachable"] for g in gateways),
        "pending": sms.pending_count(),
        "retry_interval": cfg.get("SMS_RETRY_INTERVAL"),
        "template": cfg.get("SMS_TEMPLATE") or "",
    })


@bp.route("/sms/config", methods=["GET"])
@admin_required
def sms_config():
    """短信网关当前配置（脱敏，管理端展示用）。"""
    cfg = current_app.config
    return ok({
        "enabled": bool(cfg.get("SMS_ENABLED")),
        "gateway": cfg.get("SMS_GATEWAY_URL") or "",
        "gateways": list(cfg.get("SMS_GATEWAY_URLS") or []),
        "method": cfg.get("SMS_GATEWAY_METHOD") or "GET",
        "provider": cfg.get("SMS_PROVIDER") or "template",
        "has_token": bool(cfg.get("SMS_GATEWAY_TOKEN")),
        "template": cfg.get("SMS_TEMPLATE") or "",
        "timeout": cfg.get("SMS_GATEWAY_TIMEOUT"),
        "pending": sms.pending_count(),
    })


@bp.route("/admins", methods=["GET"])
@super_required
def admins_list():
    """现任管理员清单（含超级管理员）。"""
    rows = User.query.filter(User.role.in_(("admin", "superadmin")))         .order_by(User.student_id.asc()).all()
    return ok([u.to_dict() for u in rows])


@bp.route("/users/search", methods=["GET"])
@admin_required
def users_search():
    """按学号/姓名/手机/邮箱搜索普通用户（消息通知发送、添加管理员共用）。"""
    kw = (request.args.get("keyword") or "").strip()
    if not kw:
        return ok([])
    like = f"%{kw}%"
    rows = User.query.filter(
        User.role == "user",
        or_(
            User.student_id.like(like),
            User.name.like(like),
            User.phone.like(like),
            User.email.like(like),
        ),
    ).order_by(User.student_id.asc()).limit(20).all()
    return ok([u.to_dict() for u in rows])


@bp.route("/set-role", methods=["POST"])
@super_required
def set_role():
    """设置用户角色（仅可在 admin / user 之间切换）。

    角色在登录时是按配置里的 ADMIN_STUDENT_IDS 重新判定的，数据库 role 只是缓存，
    因此这里在改库的同时把学号同步写回 .env —— 否则下次登录会被配置覆盖。
    """
    data = request.get_json(silent=True) or {}
    student_id = (data.get("student_id") or "").strip()
    role = data.get("role")
    if role not in ("admin", "user"):
        return fail("无效的角色", code=1002)
    target = User.query.filter_by(student_id=student_id).first()
    if target is None:
        return fail("该学号尚未登录过本系统，无法设置", code=1002)
    if target.role == "superadmin" or student_id in current_app.config.get("SUPER_ADMIN_STUDENT_IDS", []):
        return fail("不能修改超级管理员的角色", code=1002)
    if target.id == g.user.id:
        return fail("不能修改自己的角色", code=1002)

    # —— 同步配置：加入 / 移出 ADMIN_STUDENT_IDS，并写回 .env ——
    prev_ids = list(current_app.config.get("ADMIN_STUDENT_IDS") or [])
    new_ids = list(prev_ids)
    if role == "admin":
        if student_id not in new_ids:
            new_ids.append(student_id)
    else:
        new_ids = [x for x in new_ids if x != student_id]

    cfg_changed = new_ids != prev_ids
    if cfg_changed:
        try:
            update_list_var("ADMIN_STUDENT_IDS", new_ids)
        except Exception:
            current_app.logger.warning("写回 ADMIN_STUDENT_IDS 失败", exc_info=True)
            return fail("配置文件写入失败，管理员未修改，请检查服务器 .env 权限", code=500,
                        http_status=500)
        current_app.config["ADMIN_STUDENT_IDS"] = new_ids

    target.role = role
    log_action(g.user.id, "set_role",
               f"{target.student_id} → {role}"
               + ("（已同步写入 ADMIN_STUDENT_IDS）" if cfg_changed else ""))
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        # 库没存上就把配置文件也还原回去，避免两边不一致
        if cfg_changed:
            try:
                update_list_var("ADMIN_STUDENT_IDS", prev_ids)
            except Exception:
                current_app.logger.warning("回滚 ADMIN_STUDENT_IDS 失败", exc_info=True)
            current_app.config["ADMIN_STUDENT_IDS"] = prev_ids
        return fail("设置失败，请重试", code=500, http_status=500)

    msg = "已设为管理员（学号已写入配置文件）" if role == "admin" else "已移除管理员（学号已从配置文件移除）"
    return ok(target.to_dict(), msg=msg)


@bp.route("/feedback/review", methods=["POST"])
@admin_required
def feedback_review():
    """审核用户反馈：approve=通过（+1 奖励）；reject=拒绝（可重新上传）。"""
    data = request.get_json(silent=True) or {}
    app_id = data.get("id")
    action = data.get("action")
    if action not in ("approve", "reject"):
        return fail("无效的审核操作", code=1002)

    app_obj = db.session.get(PrintApplication, app_id)
    if app_obj is None:
        return fail("申请不存在", code=404, http_status=404)
    if not app_obj.feedback_url or app_obj.feedback_reviewed != 0:
        return fail("该申请没有待审核的反馈", code=1002)

    # 公共管理员账号：必须登记实际操作人
    operator, err = resolve_operator(data)
    if err:
        return err

    # 奖励次数由管理员自选（0 = 仅通过不奖励）
    try:
        reward = int(data.get("reward", 1))
    except (TypeError, ValueError):
        reward = 1
    if reward < 0 or reward > 50:
        return fail("奖励次数须为 0-50", code=1002)

    if action == "approve":
        app_obj.feedback_reviewed = 1
        user = app_obj.user
        ensure_quota(user)
        # 已过期的申请：审核通过也不发放奖励
        give = reward if app_obj.expired_at is None else 0
        if give and not app_obj.feedback_rewarded:
            user.remaining_quota += give
            app_obj.feedback_rewarded = True
        if app_obj.expired_at is not None:
            notify_user(user.id, "status", "反馈审核通过",
                        f"申请 {app_obj.apply_no} 的反馈已确认（该申请已过期，不发放奖励）",
                        link=f"/application/{app_obj.id}")
            log_action(operator.id, "feedback_review",
                       f"通过 {app_obj.apply_no} 的过期补交反馈，未发放奖励"
                       + (f"（公共账号操作，操作人：{operator.name}）"
                          if getattr(g.user, "is_shared_admin", False) else ""))
            msg = "已通过（过期补交，不发放奖励）"
        else:
            notify_user(user.id, "status", "反馈审核通过",
                        (f"申请 {app_obj.apply_no} 的反馈已确认，奖励 {give} 次打印机会"
                         if give else f"申请 {app_obj.apply_no} 的反馈已确认"),
                        link=f"/application/{app_obj.id}")
            log_action(operator.id, "feedback_review",
                       f"通过 {app_obj.apply_no} 的反馈，奖励 {give} 次"
                       + (f"（公共账号操作，操作人：{operator.name}）"
                          if getattr(g.user, "is_shared_admin", False) else ""))
            msg = f"已通过，奖励 {give} 次已发放" if give else "已通过，未发放奖励"
    else:
        # 拒绝：清掉反馈（含所有图片）回到「未反馈」状态，学生可重新上传
        app_obj.feedback_reviewed = None
        app_obj.feedback_url = None
        app_obj.feedback_at = None
        FeedbackImage.query.filter_by(application_id=app_obj.id).delete()
        notify_user(app_obj.user_id, "status", "反馈未通过",
                    f"申请 {app_obj.apply_no} 的反馈未通过审核，可重新上传",
                    link=f"/application/{app_obj.id}")
        log_action(operator.id, "feedback_review",
                   f"拒绝 {app_obj.apply_no} 的反馈"
                   + (f"（公共账号操作，操作人：{operator.name}）"
                      if getattr(g.user, "is_shared_admin", False) else ""))
        msg = "已拒绝，学生可重新上传"

    db.session.commit()
    return ok(app_obj.to_dict(), msg=msg)


# —— 邮件通道（消息通知页）：发送 / 记录 / 收件箱（IMAP） ——

@bp.route("/email/send", methods=["POST"])
@admin_required
def admin_email_send():
    """发一封邮件（走 .env 的 SMTP，同步发送并把结果落发送记录）。"""
    import re as _re
    from models import EmailMessage
    from services.mailer import send_mail_now

    data = request.get_json(silent=True) or {}
    to = (data.get("to") or "").strip()
    subject = (data.get("subject") or "").strip()
    body = data.get("body") or ""

    if not _re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", to):
        return fail("收件邮箱格式不正确", code=1002)
    if not subject:
        return fail("主题不能为空", code=1002)
    if not body.strip():
        return fail("正文不能为空", code=1002)

    row = EmailMessage(to_addr=to, subject=subject[:255], body=body[:10000])
    db.session.add(row)
    ok_flag, err = send_mail_now(to, subject, body)
    row.status = "sent" if ok_flag else "failed"
    row.error = None if ok_flag else (err or "")[:500]
    log_action(g.user.id, "email_send",
               (f"发送邮件至 {to}：{subject[:60]}" if ok_flag else f"邮件发送失败 -> {to}"))
    db.session.commit()
    if not ok_flag:
        return fail(f"发送失败：{err}", code=1002)
    return ok(row.to_dict(), msg="已发送")


@bp.route("/email/list", methods=["GET"])
@admin_required
def admin_email_list():
    """邮件发送记录（最新在前，50 条）。"""
    from models import EmailMessage
    rows = EmailMessage.query.order_by(EmailMessage.id.desc()).limit(50).all()
    return ok([r.to_dict() for r in rows])


@bp.route("/email/inbox", methods=["GET"])
@admin_required
def admin_email_inbox():
    """拉取发件邮箱的收件箱（IMAP，最新 20 封）——用于快速回复学生来信。"""
    import imaplib
    import email as email_lib
    from email.header import decode_header, make_header

    def _dec(s):
        try:
            return str(make_header(decode_header(s or "")))
        except Exception:
            return s or ""

    imap_host = os.getenv("IMAP_HOST") or current_app.config.get("SMTP_HOST", "").replace("smtp.", "imap.", 1)
    imap_port = int(os.getenv("IMAP_PORT", "993") or 993)
    if not imap_host:
        return fail("未配置邮箱（请先在 .env 配置 SMTP_HOST）", code=1002)
    user = current_app.config.get("SMTP_USER", "")
    pwd = current_app.config.get("SMTP_PASS", "")

    try:
        # timeout 必须给：邮箱服务器不可达时否则会无限挂起，前端 20s 就超时报"网络异常"了
        conn = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=15)
        try:
            # 163/QQ 的 IMAP 要求客户端在登录【前】发 ID 命令，否则 SELECT 会被拒（Unsafe Login）
            imaplib.Commands["ID"] = ("NONAUTH", "AUTH", "SELECTED", "LOGOUT")
            conn._simple_command("ID", '("name" "HUST3D" "version" "1.0")')
            conn._untagged_response("OK", [None], "ID")
        except Exception:
            pass
        conn.login(user, pwd)
        typ, _sel = conn.select("INBOX", readonly=True)
        if typ != "OK":
            return fail("收件箱打开失败（服务器拒绝 SELECT）", code=1002)
        typ, data = conn.search(None, "ALL")
        ids = data[0].split()[-20:]
        items = []
        for eid in reversed(ids):
            typ, msg_data = conn.fetch(eid, "(RFC822)")
            m = email_lib.message_from_bytes(msg_data[0][1])
            frm = _dec(m.get("From", ""))
            subj = _dec(m.get("Subject", "")) or "（无主题）"
            snippet = ""
            for part in m.walk():
                if part.get_content_type() == "text/plain" and not part.get_filename():
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        snippet = payload.decode(charset, "ignore")[:140].replace(chr(13), " ").replace(chr(10), " ")
                        break
            items.append({"from": frm, "subject": subj, "snippet": snippet, "date": _dec(m.get("Date", ""))})
        try:
            conn.logout()
        except Exception:
            pass
        return ok({"items": items})
    except imaplib.IMAP4.error as e:
        return fail(f"邮箱 IMAP 登录/读取失败：{str(e)[:150]}（请确认邮箱已开启 IMAP 服务）", code=1002)
    except Exception as e:
        return fail(f"收件箱读取失败：{str(e)[:150]}", code=1002)
