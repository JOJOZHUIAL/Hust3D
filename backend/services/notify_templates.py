# -*- coding: utf-8 -*-
"""通知模板（短信 / 邮件）：可在管理端「消息通知 → 设置」里直接编辑。

存储：写回 `.env`（`NOTIFY_SMS_TEMPLATE` / `NOTIFY_EMAIL_SUBJECT` / `NOTIFY_EMAIL_TEMPLATE`）。
`.env` 是单行格式，所以换行在文件里存成字面量 `\\n`，读出来再还原成真正的换行；
保存时会先转义，写入后再更新内存配置，**改完立即生效、不用重启**。

可用占位符（渲染时逐个替换，未知占位符原样保留）：
    {name}      申请人姓名
    {apply_no}  申请编号，如 HUST3D20261026002
    {file_name} 模型/文件名
    {printer}   打印机名称（没有则为空）
    {deadline}  反馈截止时间
"""
from flask import current_app

from utils.env_file import set_var

NL = chr(10)  # 换行（避免模板里直接写转义字符）

DEFAULT_SMS = (
    "【3D打印服务】{name}同学，您的打印件（{apply_no}）已打印完成，"
    "请携带校园卡到创新创业协会工作室领取。"
)
DEFAULT_EMAIL_SUBJECT = "【3D打印服务】你的打印件已完成，请领取"
DEFAULT_EMAIL = (
    "{name} 同学：\n\n"
    "你提交的申请（{apply_no}）已打印完成，请携带校园卡到创新创业协会工作室领取。\n\n"
    "领取后欢迎上传实物图反馈，成功可奖励 1 次打印机会。\n\n"
    "理工智造共享平台 · 大学生创新创业协会"
)

# —— 反馈提醒模板（未过期 / 已过期）——
DEFAULT_SMS_REMIND = (
    "【3D打印服务】{name}同学，你的打印件（{apply_no}）已完成 {days} 天还未收到反馈，"
    "请在 {deadline} 前登录平台上传实物照片，奖励 1 次打印机会。"
)
DEFAULT_SMS_REMIND_EXPIRED = (
    "【3D打印服务】{name}同学，你的打印件（{apply_no}）反馈已超过 {days} 天期限"
    "（截止 {deadline}），仍可补交实物照片，补交后需管理员审核。"
)
DEFAULT_EMAIL_REMIND_SUBJECT = "【3D打印服务】反馈提醒：申请 {apply_no}"
DEFAULT_EMAIL_REMIND = NL.join([
    "{name} 同学：",
    "",
    "你提交的申请（{apply_no}）{state}，请登录平台上传打印件实物图 / 现场照片。",
    "反馈截止：{deadline}（已完成 {days} 天）。",
    "",
    "未过期提交审核通过可奖励 1 次打印机会；已过期补交需管理员审核。",
    "",
    "理工智造共享平台 · 大学生创新创业协会",
])

KEYS = {
    "sms": ("NOTIFY_SMS_TEMPLATE", DEFAULT_SMS),
    "email_subject": ("NOTIFY_EMAIL_SUBJECT", DEFAULT_EMAIL_SUBJECT),
    "email_body": ("NOTIFY_EMAIL_TEMPLATE", DEFAULT_EMAIL),
    "sms_remind": ("NOTIFY_SMS_REMIND", DEFAULT_SMS_REMIND),
    "sms_remind_expired": ("NOTIFY_SMS_REMIND_EXPIRED", DEFAULT_SMS_REMIND_EXPIRED),
    "email_remind_subject": ("NOTIFY_EMAIL_REMIND_SUBJECT", DEFAULT_EMAIL_REMIND_SUBJECT),
    "email_remind_body": ("NOTIFY_EMAIL_REMIND", DEFAULT_EMAIL_REMIND),
}

PLACEHOLDERS = ["{name}", "{apply_no}", "{file_name}", "{printer}", "{deadline}", "{days}", "{state}"]


def _unescape(raw):
    """文件里存的是字面量 \\n，这里还原成换行。"""
    return (raw or "").replace("\\r\\n", "\n").replace("\\n", "\n")


def _escape(text):
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")


def get_raw(kind):
    """取模板原文（已还原换行）；没配就用默认值。"""
    key, default = KEYS[kind]
    raw = current_app.config.get(key)
    if raw is None or str(raw).strip() == "":
        if kind == "sms":
            # 兼容老配置：SMS_TEMPLATE
            legacy = current_app.config.get("SMS_TEMPLATE")
            if legacy:
                return _unescape(legacy)
        return default
    return _unescape(str(raw))


def all_templates():
    return {
        "sms": get_raw("sms"),
        "email_subject": get_raw("email_subject"),
        "email_body": get_raw("email_body"),
        "sms_remind": get_raw("sms_remind"),
        "sms_remind_expired": get_raw("sms_remind_expired"),
        "email_remind_subject": get_raw("email_remind_subject"),
        "email_remind_body": get_raw("email_remind_body"),
        "placeholders": PLACEHOLDERS,
    }


def save(sms=None, email_subject=None, email_body=None,
         sms_remind=None, sms_remind_expired=None,
         email_remind_subject=None, email_remind_body=None):
    """保存模板（None 表示不改），写回 .env 并立即更新内存。"""
    cfg = current_app.config
    updates = {
        "sms": (sms, "NOTIFY_SMS_TEMPLATE"),
        "email_subject": (email_subject, "NOTIFY_EMAIL_SUBJECT"),
        "email_body": (email_body, "NOTIFY_EMAIL_TEMPLATE"),
        "sms_remind": (sms_remind, "NOTIFY_SMS_REMIND"),
        "sms_remind_expired": (sms_remind_expired, "NOTIFY_SMS_REMIND_EXPIRED"),
        "email_remind_subject": (email_remind_subject, "NOTIFY_EMAIL_REMIND_SUBJECT"),
        "email_remind_body": (email_remind_body, "NOTIFY_EMAIL_REMIND"),
    }
    for kind, (value, key) in updates.items():
        if value is None:
            continue
        text = str(value).strip()
        set_var(key, _escape(text))
        cfg[key] = _escape(text)  # 内存里也存转义后的形式，读取时统一还原
        if kind == "sms":
            cfg["SMS_TEMPLATE"] = _unescape(text)  # 让老的读取路径也一致
    return all_templates()


def render(template, **ctx):
    """占位符替换；未知占位符原样保留。"""
    out = template or ""
    for key, val in ctx.items():
        out = out.replace("{" + key + "}", "" if val is None else str(val))
    return out


# ---------------------------------------------------------------- 业务快捷渲染

def _app_ctx(app_obj, printer=None):
    user = getattr(app_obj, "user", None)
    try:
        deadline = app_obj.feedback_deadline()
        deadline_text = deadline.strftime("%Y-%m-%d %H:%M") if deadline else ""
    except Exception:
        deadline_text = ""
    return {
        "name": (user.name if user else "") or "同学",
        "apply_no": app_obj.apply_no,
        "file_name": app_obj.file_name or "",
        "printer": printer or app_obj.printer_name or "",
        "deadline": deadline_text,
    }


def render_pickup_sms(app_obj):
    return render(get_raw("sms"), **_app_ctx(app_obj)).strip()


def render_pickup_email(app_obj, printer=None):
    ctx = _app_ctx(app_obj, printer)
    return render(get_raw("email_subject"), **ctx).strip(), render(get_raw("email_body"), **ctx).strip()


def render_remind_sms(app_obj, expired=False):
    """反馈提醒短信（expired=True 用已过期模板）。"""
    return render(get_raw("sms_remind_expired" if expired else "sms_remind"),
                  **_remind_ctx(app_obj, expired)).strip()


def render_remind_email(app_obj, expired=False):
    """反馈提醒邮件（主题, 正文）。"""
    ctx = _remind_ctx(app_obj, expired)
    return (render(get_raw("email_remind_subject"), **ctx).strip(),
            render(get_raw("email_remind_body"), **ctx).strip())


def _remind_ctx(app_obj, expired):
    """提醒模板上下文：在通用上下文上补 {days} / {state}。"""
    from datetime import datetime

    ctx = _app_ctx(app_obj)
    completed = getattr(app_obj, "completed_at", None) or getattr(app_obj, "printed_at", None)
    ctx["days"] = max(0, (datetime.now() - completed).days) if completed else 0
    ctx["state"] = "已超过反馈期限" if expired else "还未收到实物图反馈"
    return ctx
