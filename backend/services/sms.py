# -*- coding: utf-8 -*-
"""短信通知：打印完成后给申请人发取件短信，并支持管理员自定义发送。

发送方式：服务器把「手机号 + 正文」通过 HTTP 交给一台装了短信网关 App 的手机
（SmsForwarder 的「主动控制 / HttpServer」），由那台手机发短信。

手机是个人机，经常不在协会网络里 → 网关会连不上。所以所有短信统一先落库到
sms_messages 表：立即尝试发送，连不上就留在 pending，由后台线程定时重试，
等手机回到局域网（或隧道恢复）时自动补发，不会丢消息。

配置（.env）见 backend/.env.example 的 SMS_* 段。
"""
import json
import re
import threading
from datetime import datetime, timedelta
from urllib.parse import quote

import requests
from flask import current_app

from extensions import db
from models import PrintApplication, SmsMessage
from services.logger import log_action

PHONE_RE = re.compile(r"^1\d{10}$")

# 模块级引用，便于测试里替换（不要在用的时候直接写死 requests.get）
_http_get = requests.get
_http_post = requests.post

# 网关不可达时的重试退避（分钟）：1, 3, 5, 10, 20, 30, 60，之后固定 60
RETRY_BACKOFF = [1, 3, 5, 10, 20, 30, 60]


def _cfg(app=None):
    cfg = (app or current_app).config
    urls = cfg.get("SMS_GATEWAY_URLS") or []
    if not urls:
        one = (cfg.get("SMS_GATEWAY_URL") or "").strip()
        urls = [one] if one else []
    if (cfg.get("SMS_PROVIDER") or "").strip().lower() == "smshub":
        urls = []  # sms-hub 用 SMSHUB_BASE_URL，不走网关列表
    return {
        "enabled": bool(cfg.get("SMS_ENABLED")),
        "urls": list(urls),
        "url": urls[0] if urls else "",
        "method": (cfg.get("SMS_GATEWAY_METHOD") or "GET").upper(),
        "provider": (cfg.get("SMS_PROVIDER") or "template").lower(),
        "json": cfg.get("SMS_JSON_TEMPLATE") or "",
        "token": cfg.get("SMS_GATEWAY_TOKEN") or "",
        "timeout": int(cfg.get("SMS_GATEWAY_TIMEOUT") or 8),
        "insecure": bool(cfg.get("SMS_GATEWAY_INSECURE")),
        "template": cfg.get("SMS_TEMPLATE") or "",
    }


# ---------------------------------------------------------------- 渲染


def _fill(template, mapping):
    """把 {key} 占位符替换成实际值（不解析其它花括号，避免模板里的大括号报错）。"""
    out = template or ""
    for key, val in mapping.items():
        out = out.replace("{" + key + "}", "" if val is None else str(val))
    return out


def _json_str(val):
    """把字符串转成可以安全嵌进 JSON 模板的内容（去掉外层引号）。"""
    return json.dumps("" if val is None else str(val), ensure_ascii=False)[1:-1]


def _snip(resp, limit=80):
    """截取网关返回体的一小段，便于排查。"""
    try:
        text = (resp.text or "").strip().replace("\n", " ")
        return text[:limit]
    except Exception:
        return ""


def build_message(app_obj, template=None):
    """渲染取件短信正文（模板可在「消息通知 → 设置」里编辑）。"""
    if template is None:
        from services import notify_templates
        return notify_templates.render_pickup_sms(app_obj)
    return _fill(template, {
        "name": app_obj.user.name if app_obj.user else "",
        "apply_no": app_obj.apply_no,
        "file_name": app_obj.file_name or "",
    }).strip()


def build_feedback_remind_message(app_obj, expired=None):
    """渲染反馈提醒短信正文（未反馈/已过期的申请，管理员手动发送）。

    走「消息通知 → 设置」里可编辑的两套模板：
      未过期 → NOTIFY_SMS_REMIND；已过期 → NOTIFY_SMS_REMIND_EXPIRED。
    expired=None 时按申请当前是否已过期自动选择。
    """
    from services import notify_templates

    if expired is None:
        expired = getattr(app_obj, "expired_at", None) is not None
    return notify_templates.render_remind_sms(app_obj, expired=bool(expired))


def build_url(cfg, phone, message):
    """渲染网关地址（手机号与正文做 URL 编码）。"""
    return _fill(cfg["url"], {
        "phone": quote(phone, safe=""),
        "msg": quote(message, safe=""),
        "token": quote(cfg["token"], safe=""),
    })


# ---------------------------------------------------------------- 发送


def deliver(cfg, phone, message):
    """按顺序尝试每个网关，返回 (是否成功, 结果说明, 是否「全部不可达」, 使用的网关)。

    多个监听窗口（SMS_GATEWAY_URL / _2 / ...）：谁在线就用谁，都不在线则由调用方入队重试。
    """
    if not cfg["enabled"]:
        return False, "未启用短信通知（SMS_ENABLED=0）", False, None
    if cfg["provider"] == "smshub":
        # sms-hub 自带令牌/重试，不需要网关列表
        ok, detail, unreachable = _deliver_one(cfg, "", phone, message)
        return ok, detail, unreachable, "sms-hub"
    if not cfg["urls"]:
        return False, "未配置短信网关地址（SMS_GATEWAY_URL）", False, None
    if not PHONE_RE.match(phone or ""):
        return False, "手机号格式不正确，未发送", False, None

    errors = []
    any_unreachable = False
    for url in cfg["urls"]:
        ok, detail, unreachable = _deliver_one(cfg, url, phone, message)
        if ok:
            return True, detail, False, url
        any_unreachable = any_unreachable or unreachable
        errors.append(f"{url} → {detail}")

    # 有网关只是「连不上」→ 值得等它回来；全部都是明确的错误 → 不必重试
    combined = "；".join(errors)[:250]
    return False, combined, any_unreachable, None


def _deliver_one(cfg, url, phone, message):
    """向单个网关发送，返回 (是否成功, 结果说明, 是否「不可达」)。"""
    wait = cfg["timeout"]
    verify = not cfg.get("insecure")
    if not verify:
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

    # —— 通道零：sms-hub（ESP32C3 + 4G 模组短信网关，推荐）——
    if cfg["provider"] == "smshub":
        from services import sms_hub

        if not PHONE_RE.match(phone or ""):
            return False, "手机号格式不正确，未发送", False
        try:
            res = sms_hub.send_text(phone, message)
            return True, f"已发送（sms-hub #{res.get('id')}，{res.get('parts') or 1} 段）", False
        except sms_hub.SmsHubError as e:
            return False, str(e)[:200], bool(getattr(e, "retryable", False))
        except Exception as e:
            return False, f"发送失败：{type(e).__name__}: {str(e)[:100]}", False

    # —— 通道一：POST JSON 报文（SmsForwarder「主动控制」这类接口）——
    if cfg["provider"] == "json":
        body = _fill(cfg["json"], {
            "phone": _json_str(phone),
            "msg": _json_str(message),
            "token": _json_str(cfg["token"]),
        })
        try:
            resp = _http_post(
                url,
                data=body.encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=wait,
                verify=verify,
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout) as e:
            return False, f"网关不可达（{type(e).__name__}）", True
        except requests.exceptions.Timeout:
            return True, "已提交网关（未等到响应，请以是否收到短信为准）", False
        except Exception as e:
            return False, f"发送失败：{type(e).__name__}: {str(e)[:100]}", False

        if 200 <= resp.status_code < 300:
            text = _snip(resp, 120)
            low = text.lower()
            if "permission" in low or "权限" in text:
                return False, f"网关缺少发送权限：{text}", False
            return True, f"已发送（HTTP {resp.status_code}）{('：' + text) if text else ''}", False
        return False, f"HTTP {resp.status_code}：{_snip(resp)}", False

    # —— 通道二：URL 参数模板（通用）——
    target = build_url({"url": url, "token": cfg["token"]}, phone, message)
    if "{" in target:
        return False, "网关地址模板存在未知占位符，未发送", False
    try:
        if cfg["method"] == "POST":
            resp = _http_post(target, timeout=wait, verify=verify)
        else:
            resp = _http_get(target, timeout=wait, verify=verify)
    except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout) as e:
        return False, f"网关不可达（{type(e).__name__}）", True
    except requests.exceptions.Timeout:
        return True, "已提交网关（未等到响应）", False
    except Exception as e:
        return False, f"发送失败：{type(e).__name__}: {str(e)[:100]}", False

    if 200 <= resp.status_code < 300:
        return True, f"已发送（HTTP {resp.status_code}）", False
    return False, f"HTTP {resp.status_code}", False


def _next_retry(attempts):
    """按尝试次数算下次重试时间。"""
    minutes = RETRY_BACKOFF[min(attempts, len(RETRY_BACKOFF) - 1)]
    return datetime.now() + timedelta(minutes=minutes)


def _apply_result(msg, ok, detail, unreachable):
    """把发送结果写回记录，并同步关联申请的展示字段。"""
    msg.attempts = (msg.attempts or 0) + 1
    msg.last_error = None if ok else (detail or "")[:255]
    if ok:
        msg.status = "sent"
        msg.sent_at = datetime.now()
        msg.next_retry_at = None
        if msg.application_id:
            app_obj = db.session.get(PrintApplication, msg.application_id)
            if app_obj is not None:
                app_obj.sms_sent_at = msg.sent_at
                app_obj.sms_result = (detail or "")[:255]
    elif unreachable:
        msg.status = "pending"
        msg.next_retry_at = _next_retry(msg.attempts)
    else:
        # 配置错/号码错/网关报错这类，重试也没用 → 直接失败
        msg.status = "failed"
        msg.next_retry_at = None
        if msg.application_id:
            app_obj = db.session.get(PrintApplication, msg.application_id)
            if app_obj is not None:
                app_obj.sms_result = (detail or "")[:255]
    db.session.commit()


def try_send(msg_id):
    """尝试发送一条已入库的短信（同步），返回 (ok, detail)。"""
    msg = db.session.get(SmsMessage, msg_id)
    if msg is None:
        return False, "短信记录不存在"
    if msg.status == "sent":
        return True, "已发送过"
    cfg = _cfg()
    ok, detail, unreachable, used = deliver(cfg, msg.phone, msg.content)
    msg.gateway = used or "、".join(cfg["urls"])[:250]
    _apply_result(msg, ok, detail, unreachable)
    log_action(None, "sms_send", f"#{msg.id} → {msg.phone}：{detail}")
    return ok, detail


def enqueue(phone, content, kind="custom", application_id=None, apply_no=None,
            receiver_name=None, sender_id=None, sender_name=None):
    """把短信写入队列（不发送），返回记录。"""
    msg = SmsMessage(
        phone=(phone or "").strip(),
        content=content or "",
        kind=kind,
        application_id=application_id,
        apply_no=apply_no,
        receiver_name=receiver_name,
        status="pending",
        attempts=0,
        sender_id=sender_id,
        sender_name=sender_name,
    )
    db.session.add(msg)
    db.session.commit()
    return msg


def send_or_queue(phone, content, kind="custom", **extra):
    """入库并立即尝试；网关不可达则留在 pending 等后台重试。"""
    msg = enqueue(phone, content, kind=kind, **extra)
    ok, detail = try_send(msg.id)
    return msg, ok, detail


# ---------------------------------------------------------------- 业务入口


def notify_pickup_sms(app_obj, force=False, sync=False):
    """打印完成后给申请人发取件短信。返回短信记录 id（未启用/已发过则 None）。

    sync=False 时用后台线程发送（不阻塞业务），sync=True 时同步发送（管理端手动重发用）。
    """
    if not current_app.config.get("SMS_ENABLED"):
        return None
    # 「消息通知 → 设置」里的自动短信开关
    if not force and not current_app.config.get("NOTIFY_AUTO_SMS", True):
        return None
    if app_obj.sms_sent_at is not None and not force:
        return None
    phone = ((app_obj.user.phone if app_obj.user else "") or "").strip()
    content = build_message(app_obj)
    msg = enqueue(
        phone, content, kind="pickup",
        application_id=app_obj.id, apply_no=app_obj.apply_no,
        receiver_name=app_obj.user.name if app_obj.user else None,
    )
    if sync:
        try_send(msg.id)
        return msg.id
    app = current_app._get_current_object()
    threading.Thread(target=_worker, args=(app, msg.id), daemon=True,
                     name=f"sms-{msg.id}").start()
    return msg.id


def _worker(app, msg_id):
    """后台线程：发一条短信（失败留在队列里等重试）。"""
    try:
        with app.app_context():
            try_send(msg_id)
    except Exception:
        db.session.rollback()
        app.logger.warning("短信发送异常", exc_info=True)


def send_custom(phone, content, sender=None):
    """管理员自定义发送：入库 + 立即尝试，返回 (记录, ok, detail)。"""
    msg, ok, detail = send_or_queue(
        phone, content, kind="custom",
        sender_id=getattr(sender, "id", None),
        sender_name=getattr(sender, "name", None),
    )
    return msg, ok, detail


def test_gateway(phone):
    """给指定手机号发一条测试短信（管理端验证配置用）。"""
    content = "【3D打印服务】短信通知测试，收到即表示网关配置正确。"
    msg, ok, detail = send_or_queue(phone, content, kind="test")
    return ok, detail


# ---------------------------------------------------------------- 队列重试


def retry_pending(limit=20):
    """把到期的 pending 短信重发一遍，返回本次成功条数。"""
    if not current_app.config.get("SMS_ENABLED"):
        return 0
    now = datetime.now()
    rows = (
        SmsMessage.query
        .filter(SmsMessage.status == "pending")
        .filter((SmsMessage.next_retry_at.is_(None)) | (SmsMessage.next_retry_at <= now))
        .order_by(SmsMessage.id.asc())
        .limit(limit)
        .all()
    )
    done = 0
    for row in rows:
        try:
            ok, _detail = try_send(row.id)
            if ok:
                done += 1
        except Exception:
            db.session.rollback()
    return done


def pending_count():
    return SmsMessage.query.filter_by(status="pending").count()


URL_RE = re.compile(r"^https?://[^\s/]+(/[^\s]*)?$", re.I)


def normalize_url(url):
    """校验并规范化网关地址（返回 None 表示不合法）。"""
    u = (url or "").strip()
    if not u or not URL_RE.match(u):
        return None
    return u


def gateway_list():
    """当前生效的监听窗口列表。"""
    return list(_cfg()["urls"])


def save_gateways(urls):
    """把监听窗口列表写回 .env，并立即更新内存里的配置（无需重启）。"""
    from utils.env_file import set_indexed_vars

    clean = []
    for u in urls:
        v = normalize_url(u)
        if v and v not in clean:
            clean.append(v)

    set_indexed_vars("SMS_GATEWAY_URL", clean)
    cfg = current_app.config
    cfg["SMS_GATEWAY_URLS"] = clean
    cfg["SMS_GATEWAY_URL"] = clean[0] if clean else ""
    return clean


def add_gateway(url):
    """新增一个监听窗口。返回 (列表, 错误说明)。"""
    v = normalize_url(url)
    if not v:
        return gateway_list(), "地址格式不正确（应形如 http://192.168.1.130:5000/sms/send）"
    urls = gateway_list()
    if v in urls:
        return urls, "该监听窗口已存在"
    urls.append(v)
    return save_gateways(urls), None


def remove_gateway(url):
    """删除一个监听窗口。返回 (列表, 错误说明)。"""
    v = normalize_url(url) or (url or "").strip()
    urls = gateway_list()
    if v not in urls:
        return urls, "该监听窗口不存在"
    urls.remove(v)
    return save_gateways(urls), None


def probe_gateway(timeout=3):
    """逐个探测网关是否可达（只做连通性判断，不发短信）。

    返回 [{"url":..., "reachable": bool}]。
    """
    cfg = _cfg()
    if cfg["provider"] == "smshub":
        from services import sms_hub
        base = (current_app.config.get("SMSHUB_BASE_URL") or "").rstrip("/")
        return [{"url": base or "sms-hub", "reachable": sms_hub.probe(timeout)}]
    result = []
    for url in cfg["urls"]:
        result.append({"url": url, "reachable": _probe_one(url, timeout)})
    return result


def _probe_one(url, timeout=3):
    try:
        from urllib.parse import urlparse
        import socket
        u = urlparse(url)
        host = u.hostname
        port = u.port or (443 if u.scheme == "https" else 80)
        if not host:
            return False
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def start_retry_worker(app):
    """启动后台重试线程（网关恢复后自动补发）。"""
    interval = int(app.config.get("SMS_RETRY_INTERVAL") or 60)
    if interval <= 0:
        return None

    def loop():
        import time
        while True:
            time.sleep(interval)
            try:
                with app.app_context():
                    n = retry_pending()
                    if n:
                        app.logger.info("短信队列补发成功 %s 条", n)
            except Exception:
                app.logger.warning("短信队列重试失败", exc_info=True)

    t = threading.Thread(target=loop, daemon=True, name="sms-retry")
    t.start()
    return t
