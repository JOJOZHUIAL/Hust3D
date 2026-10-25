# -*- coding: utf-8 -*-
"""SMTP 发信自检：用 .env 里的配置发一封测试邮件，失败时打印真实原因。

用法：
    .venv\\Scripts\\python.exe scripts\\test_mail.py 收件人邮箱
例如：
    .venv\\Scripts\\python.exe scripts\\test_mail.py 2580333518@qq.com
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import smtplib
from email.header import Header
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

HOST = os.getenv("SMTP_HOST", "")
PORT = int(os.getenv("SMTP_PORT", "465"))
USER = os.getenv("SMTP_USER", "")
PASS = os.getenv("SMTP_PASS", "")
SENDER = os.getenv("SMTP_SENDER", "") or USER


def main():
    if len(sys.argv) < 2:
        print("用法：python scripts/test_mail.py 收件人邮箱")
        return 1
    to = sys.argv[1].strip()

    if not HOST or not USER:
        print("[失败] .env 里还没有配置 SMTP_HOST / SMTP_USER，请先填写（参考 .env 里的注释模板）。")
        return 1

    print(f"发送配置：{HOST}:{PORT} | 账号 {USER} | 发件人 {SENDER}")
    print(f"收件人：{to}")

    msg = MIMEText("这是一封测试邮件。收到说明邮件通知功能已配置成功：\n"
                   "打印完成 / 打印失败时，系统会自动向申请人邮箱发送通知。", "plain", "utf-8")
    msg["Subject"] = Header("【3D打印服务】邮件通知测试", "utf-8")
    msg["From"] = SENDER
    msg["To"] = to

    try:
        if PORT == 465:
            server = smtplib.SMTP_SSL(HOST, PORT, timeout=15)
        else:
            server = smtplib.SMTP(HOST, PORT, timeout=15)
            server.starttls()
        server.login(USER, PASS)
        server.sendmail(SENDER, [to], msg.as_string())
        server.quit()
        print("[成功] 测试邮件已发送，请到收件箱（或垃圾邮件）查收。")
        print("       后端重启后，打印完成 / 打印失败的邮件通知即自动生效。")
        return 0
    except smtplib.SMTPAuthenticationError:
        print("[失败] 登录被拒绝：账号或密码错误。")
        print("       QQ 邮箱必须使用「授权码」而不是登录密码（设置 → 账户 → 开启 SMTP → 生成授权码）。")
        return 1
    except Exception as e:
        print(f"[失败] {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
