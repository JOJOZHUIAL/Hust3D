# -*- coding: utf-8 -*-
"""邮件通知：SMTP 异步发送（后台线程，失败仅记日志、不影响主流程）。

为什么要做这么多校验 —— 之前退信爆炸（一次几十封 PostMaster 退信）的三个原因：
  1. 收件人是 `student@example.com` 这类占位地址，域名根本不存在（No MX Record Found）；
  2. 邮件头缺 Date / Message-ID，部分邮箱判为畸形邮件；
  3. 同一个坏地址每次事件都重发，越攒越多。

现在的策略：
  - 地址格式校验 + 明显假的域名（example.com / test.com / .local 等）直接跳过；
  - 域名 MX 预检（带缓存），查不到 MX 就不发（这类必然退信）；
  - 发送失败计数：同一地址连续失败 MAIL_MAX_FAILS 次后自动拉黑 MAIL_BLOCK_HOURS 小时；
  - 补全 Date / Message-ID / MIME-Version 头；
  - 全局限流：每分钟最多 MAIL_RATE_PER_MIN 封。
SMTP 未配置（.env 无 SMTP_HOST）或收件人为空时静默跳过。
"""
import re
import smtplib
import threading
import time
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

from flask import current_app

# 明显的占位/内网域名：这些域名发出去 100% 退信，直接跳过
FAKE_DOMAINS = {
    "example.com", "example.org", "example.net", "example.edu",
    "test.com", "test.local", "localhost", "localhost.localdomain",
    "invalid", "domain.com", "email.com", "mail.com", "none.com",
    "123.com", "abc.com", "1.com", "a.com", "local", "localdomain",
}
FAKE_SUFFIXES = (".local", ".localdomain", ".invalid", ".test", ".example", ".lan", ".internal")

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

# 运行期状态：失败计数 / 拉黑 / 限流（进程内，重启清零）
_lock = threading.Lock()
_fails = {}       # email -> (连续失败次数, 最后一次失败时间)
_blocked = {}     # email -> 解锁时间戳
_sent_log = []    # 最近发送时间戳（限流用）
_mx_cache = {}    # domain -> (是否有 MX, 检查时间)

_MX_TTL = 6 * 3600


def _config():
    c = current_app.config
    return {
        "host": c.get("SMTP_HOST", ""),
        "port": int(c.get("SMTP_PORT", 465) or 465),
        "user": c.get("SMTP_USER", ""),
        "pwd": c.get("SMTP_PASS", ""),
        "sender": c.get("SMTP_SENDER") or c.get("SMTP_USER", ""),
        "max_fails": int(c.get("MAIL_MAX_FAILS", 3) or 3),
        "block_hours": float(c.get("MAIL_BLOCK_HOURS", 24) or 24),
        "rate_per_min": int(c.get("MAIL_RATE_PER_MIN", 20) or 20),
        "check_mx": bool(c.get("MAIL_CHECK_MX", True)),
    }


def is_deliverable_address(email):
    """格式 + 明显假域名检查；返回 (是否可用, 原因)。"""
    addr = (email or "").strip()
    if not addr:
        return False, "地址为空"
    if not EMAIL_RE.match(addr):
        return False, "格式不正确"
    domain = addr.rsplit("@", 1)[-1].lower()
    if domain in FAKE_DOMAINS:
        return False, "占位域名（不会收信）"
    if any(domain.endswith(s) for s in FAKE_SUFFIXES):
        return False, "内网/测试域名（不会收信）"
    return True, ""


def _domain_has_mx(domain, cfg):
    """域名可收信预检（带缓存）。

    优先查 MX（需要 dnspython）；没装就退化为「域名能否解析出 A/AAAA」——
    连 DNS 都解析不了的域名（拼错的、编的）必然退信，这类直接跳过。
    """
    if not cfg["check_mx"]:
        return True
    now = time.time()
    hit = _mx_cache.get(domain)
    if hit and now - hit[1] < _MX_TTL:
        return hit[0]

    ok = True
    try:
        import dns.resolver  # dnspython（可选依赖）
        try:
            ok = bool(dns.resolver.resolve(domain, "MX", lifetime=4))
        except Exception:
            ok = False
    except Exception:
        # 没有 dnspython：退化为 DNS 解析检查
        import socket
        try:
            socket.getaddrinfo(domain, 25, proto=socket.IPPROTO_TCP)
            ok = True
        except Exception:
            ok = False

    _mx_cache[domain] = (ok, now)
    return ok


def _is_blocked(email, cfg):
    now = time.time()
    with _lock:
        until = _blocked.get(email)
        if until and until > now:
            return True
        if until and until <= now:
            _blocked.pop(email, None)
            _fails.pop(email, None)
    return False


def _note_result(email, ok, cfg):
    with _lock:
        if ok:
            _fails.pop(email, None)
            return
        n = _fails.get(email, (0, 0))[0] + 1
        _fails[email] = (n, time.time())
        if n >= cfg["max_fails"]:
            _blocked[email] = time.time() + cfg["block_hours"] * 3600


def _rate_ok(cfg):
    now = time.time()
    with _lock:
        while _sent_log and now - _sent_log[0] > 60:
            _sent_log.pop(0)
        if len(_sent_log) >= cfg["rate_per_min"]:
            return False
        _sent_log.append(now)
        return True


def _deliver(to, subject, body, cfg):
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = cfg["sender"]
        msg["To"] = to
        # 补齐标准头：缺 Date 的邮件会被判为畸形（退信里显示 1970-01-01 就是这个原因）
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=cfg["sender"].rsplit("@", 1)[-1] or "localhost")
        msg["MIME-Version"] = "1.0"

        if cfg["port"] == 465:
            server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=15)
        else:
            server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=15)
            server.starttls()
        if cfg["user"]:
            server.login(cfg["user"], cfg["pwd"])
        server.sendmail(cfg["sender"], [to], msg.as_string())
        server.quit()
        print(f"[MAIL] 已发送至 {to}: {subject}")
        _note_result(to, True, cfg)
    except Exception as e:
        print(f"[MAIL] 发送失败 -> {to}: {e}")
        _note_result(to, False, cfg)


def send_mail_async(to, subject, body):
    """异步发送邮件；未配置 SMTP / 地址无效 / 被拉黑 / 超限时静默跳过。"""
    email = (to or "").strip()
    if not email:
        return
    cfg = _config()
    if not cfg["host"] or not cfg["user"]:
        return  # 未配置 SMTP，静默跳过
    # 「消息通知 → 设置」里的自动邮件开关
    if not current_app.config.get("NOTIFY_AUTO_EMAIL", True):
        return

    ok, reason = is_deliverable_address(email)
    if not ok:
        print(f"[MAIL] 跳过 {email}：{reason}")
        return
    domain = email.rsplit("@", 1)[-1].lower()
    if not _domain_has_mx(domain, cfg):
        print(f"[MAIL] 跳过 {email}：域名 {domain} 没有 MX 记录（发出去必然退信）")
        return
    if _is_blocked(email, cfg):
        print(f"[MAIL] 跳过 {email}：连续退信已被临时拉黑")
        return
    if not _rate_ok(cfg):
        print("[MAIL] 跳过：每分钟发送量已达上限")
        return

    threading.Thread(target=_deliver, args=(email, subject, body, cfg), daemon=True).start()


def send_mail_now(to, subject, body):
    """同步发送一封邮件，返回 (是否成功, 错误信息)。

    供管理端「消息通知 → 发送邮件」使用（需要把结果落到发送记录），
    与 send_mail_async 共用全部防护检查（格式 / 假域名 / MX / 拉黑 / 限流）。
    """
    email = (to or "").strip()
    if not email:
        return False, "收件人为空"
    cfg = _config()
    if not cfg["host"] or not cfg["user"]:
        return False, "未配置 SMTP"
    ok, reason = is_deliverable_address(email)
    if not ok:
        return False, reason
    domain = email.rsplit("@", 1)[-1].lower()
    if not _domain_has_mx(domain, cfg):
        return False, f"域名 {domain} 没有 MX 记录（发出去必然退信）"
    if _is_blocked(email, cfg):
        return False, "该地址连续退信已被临时拉黑"
    if not _rate_ok(cfg):
        return False, "每分钟发送量已达上限，请稍后再试"
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = cfg["sender"]
        msg["To"] = email
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=cfg["sender"].rsplit("@", 1)[-1] or "localhost")
        msg["MIME-Version"] = "1.0"
        if cfg["port"] == 465:
            server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20)
        else:
            server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=20)
            server.starttls()
        if cfg["user"]:
            server.login(cfg["user"], cfg["pwd"])
        server.sendmail(cfg["sender"], [email], msg.as_string())
        server.quit()
        _note_result(email, True, cfg)
        return True, ""
    except Exception as e:
        _note_result(email, False, cfg)
        return False, str(e)
