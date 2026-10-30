# -*- coding: utf-8 -*-
"""原生短信 / 消息通知模块的 API（替代 sms-hub 的全套路由与 React 前端）。

    GET  /api/admin/native-sms/status      → 设备状态 + 自动识别到的 SIM 卡
    GET  /api/admin/native-sms/messages    → 收件箱（联系人/内容/备注搜索）
    GET  /api/admin/native-sms/outbound    → 发送记录
    POST /api/admin/native-sms/send        → 发送短信
    GET  /api/admin/native-sms/settings    → 自动短信 / 自动邮件开关
    PUT  /api/admin/native-sms/settings    → 保存开关

只有 6 个端点，全部读 SQLite / 调内部发送函数，不经过 sms-hub 的 FastAPI 层。
"""
from flask import Blueprint, g, request

from services import native_sms
from services.logger import log_action
from utils.auth import admin_required
from utils.response import fail, ok

bp = Blueprint("native_sms", __name__)


@bp.route("/status", methods=["GET"])
@admin_required
def status():
    """设备在线 / 信号 / 当前号码 / 自动识别到的卡列表。"""
    data = native_sms.status()
    data.update(native_sms.auto_flags())
    return ok(data)


@bp.route("/log", methods=["GET"])
@admin_required
def device_log():
    """固件日志（增量拉取；?since= 上次最大 seq）。"""
    try:
        since = int(request.args.get("since") or 0)
    except ValueError:
        since = 0
    return ok(native_sms.device_log(since))


@bp.route("/pull", methods=["POST"])
@admin_required
def pull_now():
    """强制让设备立刻上报一次短信。"""
    res = native_sms.pull_now()
    if res.get("ok") is False:
        return fail(f"拉取失败：{res.get('error')}", code=1002)
    log_action(g.user.id, "native_sms_pull", f"强制拉取，新增 {res.get('new_messages')} 条")
    return ok(res, msg=f"已拉取，新增 {res.get('new_messages')} 条")


@bp.route("/messages", methods=["GET"])
@admin_required
def messages():
    try:
        limit = int(request.args.get("limit") or 50)
    except ValueError:
        limit = 50
    before = request.args.get("before_id")
    items = native_sms.messages(
        limit=limit,
        before_id=int(before) if before else None,
        keyword=(request.args.get("keyword") or "").strip() or None,
    )
    return ok({"items": items, "total": native_sms.message_count()})


@bp.route("/outbound", methods=["GET"])
@admin_required
def outbound():
    try:
        limit = int(request.args.get("limit") or 50)
    except ValueError:
        limit = 50
    before = request.args.get("before_id")
    items = native_sms.outbound(limit=limit, before_id=int(before) if before else None)
    return ok({"items": items})


@bp.route("/send", methods=["POST"])
@admin_required
def send():
    data = request.get_json(silent=True) or {}
    phone = (data.get("phone") or "").strip()
    text = (data.get("text") or "").strip()
    try:
        res = native_sms.send(phone, text)
    except ValueError as e:
        return fail(str(e), code=1002)
    except Exception as e:
        return fail(f"发送失败：{type(e).__name__}: {str(e)[:120]}", code=1002)

    log_action(g.user.id, "native_sms_send", f"发送短信 → {phone}（#{res.get('id')}）")
    return ok(res, msg="已提交发送")


@bp.route("/settings", methods=["GET"])
@admin_required
def get_settings():
    from services import notify_templates

    data = native_sms.auto_flags()
    data.update({"templates": notify_templates.all_templates()})
    return ok(data)


@bp.route("/settings", methods=["PUT"])
@admin_required
def put_settings():
    """保存自动通知开关和/或短信、邮件模板（都写回 .env，立即生效）。"""
    from services import notify_templates

    data = request.get_json(silent=True) or {}
    sms_flag = data.get("auto_sms")
    email_flag = data.get("auto_email")
    tpl = data.get("templates") or {}

    changed = []
    if sms_flag is not None or email_flag is not None:
        flags = native_sms.save_auto_flags(
            auto_sms=bool(sms_flag) if sms_flag is not None else None,
            auto_email=bool(email_flag) if email_flag is not None else None,
        )
        changed.append(f"短信={'开' if flags['auto_sms'] else '关'}")
        changed.append(f"邮件={'开' if flags['auto_email'] else '关'}")

    if tpl:
        if "email_subject" in tpl and not str(tpl["email_subject"]).strip():
            return fail("邮件主题不能为空", code=1002)
        if "sms" in tpl and not str(tpl["sms"]).strip():
            return fail("短信模板不能为空", code=1002)
        if "email_body" in tpl and not str(tpl["email_body"]).strip():
            return fail("邮件模板不能为空", code=1002)
        # 反馈提醒模板：传了就校验非空（不传则不改）
        for key, label in (("sms_remind", "未过期提醒短信"),
                           ("sms_remind_expired", "已过期提醒短信"),
                           ("email_remind_subject", "提醒邮件主题"),
                           ("email_remind_body", "提醒邮件正文")):
            if key in tpl and not str(tpl[key]).strip():
                return fail(f"{label}不能为空", code=1002)

        notify_templates.save(
            sms=tpl.get("sms"),
            email_subject=tpl.get("email_subject"),
            email_body=tpl.get("email_body"),
            sms_remind=tpl.get("sms_remind"),
            sms_remind_expired=tpl.get("sms_remind_expired"),
            email_remind_subject=tpl.get("email_remind_subject"),
            email_remind_body=tpl.get("email_remind_body"),
        )
        changed.append("模板已更新")

    if not changed:
        return fail("没有需要保存的内容", code=1002)

    log_action(g.user.id, "native_sms_settings", "消息通知设置：" + "，".join(changed))
    out = native_sms.auto_flags()
    out.update({"templates": notify_templates.all_templates()})
    return ok(out, msg="已保存")
