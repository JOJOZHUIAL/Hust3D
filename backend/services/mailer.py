# -*- coding: utf-8 -*-
"""邮件通知：SMTP 异步发送（后台线程，失败仅记日志、不影响主流程）。

SMTP 未配置（.env 无 SMTP_HOST）或收件人为空时静默跳过。
"""
import smtplib
import threading
from email.header import Header
from email.mime.text import MIMEText

from flask import current_app


def _deliver(to, subject, body, cfg):
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = cfg["sender"]
        msg["To"] = to
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
    except Exception as e:
        print(f"[MAIL] 发送失败 -> {to}: {e}")


def send_mail_async(to, subject, body):
    """异步发送邮件；SMTP 未配置或收件人为空时静默跳过。"""
    if not to:
        return
    cfg = {
        "host": current_app.config.get("SMTP_HOST", ""),
        "port": current_app.config.get("SMTP_PORT", 465),
        "user": current_app.config.get("SMTP_USER", ""),
        "pwd": current_app.config.get("SMTP_PASS", ""),
        "sender": current_app.config.get("SMTP_SENDER") or current_app.config.get("SMTP_USER", ""),
    }
    if not cfg["host"] or not cfg["user"]:
        return  # 未配置 SMTP，静默跳过

    threading.Thread(target=_deliver, args=(to, subject, body, cfg), daemon=True).start()
