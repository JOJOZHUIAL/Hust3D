# -*- coding: utf-8 -*-
"""全局配置。

敏感信息（数据库密码、密钥等）一律从环境变量 / 同目录 .env 文件读取，
不要硬编码到代码里，更不要提交到版本库（已在 .gitignore 中排除 .env）。
"""
import os
from dotenv import load_dotenv

# 读取同目录 .env（若存在）；生产环境也可直接 export 环境变量
load_dotenv()


def _parse_gateway_urls():
    """短信网关可以有多个监听窗口：

    SMS_GATEWAY_URL、SMS_GATEWAY_URL_2 ~ SMS_GATEWAY_URL_9，
    每项内部也能用换行或分号写多条。返回去重后的列表（保持书写顺序）。
    """
    out = []
    for suffix in [""] + [f"_{i}" for i in range(2, 10)]:
        raw = (os.getenv("SMS_GATEWAY_URL" + suffix) or "").strip()
        if not raw:
            continue
        for part in raw.replace("\r", "\n").replace(";", "\n").split("\n"):
            part = part.strip()
            if part and part not in out:
                out.append(part)
    return out


# 项目根目录（backend/ 所在位置）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    # —— 安全密钥（生产环境务必修改为随机值） ——
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    JWT_SECRET = os.getenv("JWT_SECRET", "dev-jwt-change-me")
    # 登录态有效期（秒），默认 7 天
    JWT_EXPIRES = int(os.getenv("JWT_EXPIRES", str(7 * 24 * 3600)))

    # —— 数据库 ——
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "hust_3d")
    # 支持 DATABASE_URL 整体覆盖（便于本地用 SQLite 跑冒烟测试 / CI），
    # 未设置时默认用 MySQL（pymysql）。
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 3600}

    # —— 文件上传 ——
    # 上传根目录：STL 文件、签名图片均存于此，路径以相对路径落库
    UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
    MAX_STL_SIZE = 50 * 1024 * 1024  # 50MB

    # —— 教务系统（jwzx.hrbust.edu.cn，Acegi 登录 + 图形验证码） ——
    # 本地开发开关：为 1 时不连学校系统，仅做格式校验
    CAS_MOCK = os.getenv("CAS_MOCK", "1") == "1"
    # ⚠️ 学校系统为 HTTP 明文，密码在「我方服务器 → 学校」链路上明文传输，属学校侧现状
    CAS_BASE_URL = os.getenv("CAS_BASE_URL", "http://jwzx.hrbust.edu.cn")
    # 建立会话用的首页（拿到 JSESSIONID）
    CAS_HOMEPAGE_URL = os.getenv("CAS_HOMEPAGE_URL", "/homepage/index.do")
    # 验证码图片地址
    CAS_CAPTCHA_URL = os.getenv("CAS_CAPTCHA_URL", "/academic/getCaptcha.do")
    # 登录提交地址（Acegi 统一认证）
    CAS_LOGIN_URL = os.getenv("CAS_LOGIN_URL", "/academic/j_acegi_security_check")
    # 登录成功后用于抓取姓名/学院的页面：学籍信息（<th>标签</th><td>值</td> 结构）
    CAS_INFO_URL = os.getenv("CAS_INFO_URL", "/academic/accessModule.do?moduleId=2060&groupId=")
    # 调试开关：为 1 时登录后打印学籍页的字段标签名（仅标签、不含值），用于定位学院字段
    CAS_DEBUG = os.getenv("CAS_DEBUG", "0") == "1"

    # —— 业务 ——
    DEFAULT_QUOTA = int(os.getenv("DEFAULT_QUOTA", "2"))  # 每学期默认打印次数
    # 反馈奖励模式：auto=上传成功自动 +1；review=管理员审核通过后手动 +1
    FEEDBACK_REWARD_MODE = os.getenv("FEEDBACK_REWARD_MODE", "auto")

    # —— 邮件通知（打印完成后自动发邮件提醒领取；不配置则不发） ——
    # 示例（QQ 邮箱）：SMTP_HOST=smtp.qq.com  SMTP_PORT=465  SMTP_USER=xxx@qq.com
    # SMTP_PASS=授权码（不是登录密码）
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASS = os.getenv("SMTP_PASS", "")
    SMTP_SENDER = os.getenv("SMTP_SENDER", "") or SMTP_USER
    # 反馈有效期：打印完成后多少天内未反馈即标记为已过期（状态仍是已完成，
    # 只是不能再上传反馈、不再发放奖励）；0 表示关闭该机制。
    FEEDBACK_EXPIRE_DAYS = int(os.getenv("FEEDBACK_EXPIRE_DAYS", "7"))

    # —— 打印机进度自动完成 ——
    # 绑定打印机后是否开启后台监视：进度到 100%（或状态机 FINISH）自动标记打印完成
    PRINT_WATCH_ENABLED = os.getenv("PRINT_WATCH_ENABLED", "1") == "1"
    # 监视轮询间隔（秒）
    PRINT_WATCH_INTERVAL = int(os.getenv("PRINT_WATCH_INTERVAL", "5"))

    # —— 短信通知（打印完成后通知申请人取件）——
    # 用手机上的 SmsForwarder 之类的网关发短信：服务器发一个 HTTP 请求给手机，手机再发短信
    SMS_ENABLED = os.getenv("SMS_ENABLED", "0") == "1"
    # 网关地址模板，支持占位符 {phone} {msg} {token}（示例见 .env.example）
    # 支持多个监听窗口：SMS_GATEWAY_URL、SMS_GATEWAY_URL_2 ... SMS_GATEWAY_URL_9，
    # 每项也可以用换行/分号分隔写多条；发送时按顺序挑第一个可用的。
    SMS_GATEWAY_URL = os.getenv("SMS_GATEWAY_URL", "")
    SMS_GATEWAY_URLS = _parse_gateway_urls()
    # 请求方式：GET 或 POST（参数仍放在 URL 模板里）
    SMS_GATEWAY_METHOD = os.getenv("SMS_GATEWAY_METHOD", "GET").upper()
    # 通道类型：template=URL 参数模板（默认）；json=POST JSON 报文（SmsForwarder 主动控制这类接口）
    SMS_PROVIDER = (os.getenv("SMS_PROVIDER") or "template").strip().lower()
    # JSON 通道的报文模板，占位符同上；值会自动做 JSON 转义
    SMS_JSON_TEMPLATE = os.getenv(
        "SMS_JSON_TEMPLATE", '{"phone":"{phone}","msg":"{msg}"}'
    )
    # 网关访问令牌（填到 {token} 占位处；网关不需要就留空）
    SMS_GATEWAY_TOKEN = os.getenv("SMS_GATEWAY_TOKEN", "")
    # 请求超时（秒）
    SMS_GATEWAY_TIMEOUT = int(os.getenv("SMS_GATEWAY_TIMEOUT", "8"))
    # 网关走 HTTPS 但证书不受信任（自签/内网穿透）时置 1，跳过证书校验
    SMS_GATEWAY_INSECURE = os.getenv("SMS_GATEWAY_INSECURE", "0") == "1"
    # 待发短信队列的重试间隔（秒），网关（手机）恢复后自动补发；0=关闭
    SMS_RETRY_INTERVAL = int(os.getenv("SMS_RETRY_INTERVAL", "60"))
    # 短信正文模板，支持 {name} {apply_no} {file_name}
    SMS_TEMPLATE = os.getenv(
        "SMS_TEMPLATE",
        "【3D打印服务】{name}同学，您的打印件（{apply_no}）已打印完成，"
        "请携带校园卡到3D打印工作室领取。",
    )
    # 管理员学号清单（逗号分隔），命中即视为管理员角色
    ADMIN_STUDENT_IDS = [s.strip() for s in os.getenv("ADMIN_STUDENT_IDS", "").split(",") if s.strip()]
    # 超级管理员学号清单：可添加/移除管理员（含于 ADMIN_STUDENT_IDS 之上使用）
    SUPER_ADMIN_STUDENT_IDS = [s.strip() for s in os.getenv("SUPER_ADMIN_STUDENT_IDS", "").split(",") if s.strip()]
    # 管理端把管理员学号写回配置文件时用的 .env 路径（可用 ENV_FILE 覆盖，测试用）
    ENV_FILE = os.getenv("ENV_FILE") or os.path.join(BASE_DIR, ".env")

    # —— 站点 ——
    # 前端地址，用于部署 / CORS 等场景（纯网页端，前端与后端分离部署）
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

    # —— 局域网 HTTPS（手机摄像头扫码需要安全上下文） ——
    # certs/ 目录下存在 cert.pem + key.pem 时，后端会额外在 HTTPS_PORT 提供 HTTPS 服务。
    # 证书用 scripts/generate_cert.bat 生成（自签名，含本机局域网 IP）。
    SSL_CERT = os.getenv("SSL_CERT", os.path.join(BASE_DIR, "certs", "cert.pem"))
    SSL_KEY = os.getenv("SSL_KEY", os.path.join(BASE_DIR, "certs", "key.pem"))
    HTTPS_PORT = int(os.getenv("HTTPS_PORT", "5443"))
