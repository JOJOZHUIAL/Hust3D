# -*- coding: utf-8 -*-
"""Flask 应用入口。

启动方式：
  开发：  python app.py
  生产：  gunicorn -w 4 -b 127.0.0.1:5000 app:app
"""
import os
import mimetypes
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from config import Config
from extensions import db

# Windows 注册表可能把 .js/.mjs 映射成 text/plain，导致浏览器 MIME 校验拒绝执行
# module 脚本（前端页面会白屏）。这里在导入阶段强制纠正关键前端资源类型。
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")
# 聊天附件常见类型：Windows 注册表缺失或映射错误时浏览器会拒绝播放/预览
mimetypes.add_type("video/webm", ".webm")
mimetypes.add_type("video/mp4", ".mp4")
mimetypes.add_type("audio/mp4", ".m4a")
mimetypes.add_type("audio/mpeg", ".mp3")
mimetypes.add_type("audio/ogg", ".ogg")
mimetypes.add_type("audio/ogg", ".opus")
mimetypes.add_type("audio/wav", ".wav")
mimetypes.add_type("text/markdown", ".md")
mimetypes.add_type("application/octet-stream", ".stl")

# 前端构建产物目录（单机 / 内网穿透直连 Flask 时用于服务 SPA）
FRONTEND_DIST = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist")
)


# 老库需要补的列：print_applications 新增字段（列名, 类型, MySQL 注释）
# 顺序即执行顺序；已存在的列会被跳过，因此可重复执行。
NEW_APPLICATION_COLUMNS = [
    ("feedback_reviewed", "TINYINT(1) NULL", "反馈审核：None=无需审核 0=待审核 1=通过"),
    ("reviewer_id", "INT NULL", "审批人 users.id"),
    ("reviewer_name", "VARCHAR(64) NULL", "审批人姓名快照"),
    ("reviewer_student_id", "VARCHAR(32) NULL", "审批人学号快照"),
    ("printed_by_id", "INT NULL", "打印操作人 users.id"),
    ("printed_by_name", "VARCHAR(64) NULL", "打印操作人姓名快照"),
    ("printed_by_student_id", "VARCHAR(32) NULL", "打印操作人学号快照"),
    ("completed_at", "DATETIME NULL", "打印完成时间（反馈计时起点）"),
    ("expired_at", "DATETIME NULL", "反馈超时过期时间"),
    ("sms_sent_at", "DATETIME NULL", "取件短信发送成功时间"),
    ("sms_result", "VARCHAR(255) NULL", "取件短信发送结果"),
    ("file_name", "VARCHAR(255) NULL", "STL 原始文件名（展示用）"),
    ("printer_id", "INT NULL", "绑定的打印机 printers.id"),
    ("printer_name", "VARCHAR(64) NULL", "打印机名称快照"),
    ("print_state", "VARCHAR(16) NULL", "最近观察到的打印机状态 RUNNING/FINISH"),
    ("print_progress", "INT NULL", "最近观察到的打印进度 0-100"),
    ("print_actual_file", "VARCHAR(255) NULL", "打印机当前上报的真实文件名"),
    ("print_matched", "TINYINT(1) NOT NULL DEFAULT 0", "打印机当前文件是否就是本申请"),
    ("print_seen_running", "TINYINT(1) NOT NULL DEFAULT 0", "是否已确认打印机真的开始打印"),
    ("completed_auto", "TINYINT(1) NOT NULL DEFAULT 0", "是否由打印机进度自动标记完成"),
]


def _ensure_columns():
    """老库自动补新增列（print_applications 的审批人/打印人/过期相关字段）。"""
    from sqlalchemy import inspect, text

    insp = inspect(db.engine)
    try:
        cols = {c["name"] for c in insp.get_columns("print_applications")}
    except Exception:
        return  # 表还没建（create_all 之后不会出现，防御性返回）

    missing = [(n, t, c) for n, t, c in NEW_APPLICATION_COLUMNS if n not in cols]
    if not missing:
        return

    changed = False
    for name, col_type, comment in missing:
        ddl = f"ALTER TABLE print_applications ADD COLUMN {name} {col_type}"
        if db.engine.name == "mysql" and comment:
            ddl += f" COMMENT '{comment}'"
        db.session.execute(text(ddl))
        changed = True
    if changed:
        db.session.commit()


def _lan_ips():
    """收集本机局域网 IPv4（主出口 IP 优先）。"""
    import socket

    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return ips


def _start_https(app):
    """在独立线程额外跑一个 HTTPS 服务（手机摄像头扫码用，不影响 HTTP 端口）。"""
    import threading

    port = app.config["HTTPS_PORT"]

    def run():
        try:
            app.run(
                host="0.0.0.0", port=port,
                ssl_context=(app.config["SSL_CERT"], app.config["SSL_KEY"]),
                debug=False, use_reloader=False,
            )
        except OSError as e:
            print(f"[HTTPS] {port} 端口启动失败（可能被占用）：{e}")

    threading.Thread(target=run, daemon=True, name="https-server").start()
    print(f" * HTTPS 已启用：https://<本机IP>:{port}（手机扫码用，自签名证书需点『继续访问』）")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # 开发阶段允许跨域；生产环境经 Nginx 同域代理后可按需收紧
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    db.init_app(app)

    # 确保上传根目录存在（子目录由保存逻辑按需创建）
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)

    # 启动时自动补建缺失的表（只建缺的、不动已有结构），新机器部署无需手动执行 schema.sql；
    # 完整建表脚本仍以 sql/schema.sql 为准（含注释与索引说明）
    with app.app_context():
        import models  # noqa: F401  先注册全部模型，create_all 才能建出所有表
        db.create_all()
        # 已存在的表补缺失列（新增字段时老库自动迁移）
        _ensure_columns()

        # 启动拓竹打印机状态监视（有配置打印机时建立 MQTT 连接）
        from services import bambu
        bambu.sync_with_db(app)

        # 启动「打印进度 → 自动完成」后台监视（可配置关闭，测试时关闭）
        if app.config.get("PRINT_WATCH_ENABLED"):
            from services import print_watch
            print_watch.start_watcher(app, app.config.get("PRINT_WATCH_INTERVAL", 5))

        # 启动短信队列重试：手机不在局域网时短信先存起来，网关恢复后自动补发
        if app.config.get("SMS_ENABLED"):
            from services import sms
            sms.start_retry_worker(app)

    # 注册蓝图（此处 import 避免循环依赖）
    from blueprints.auth import bp as auth_bp
    from blueprints.user import bp as user_bp
    from blueprints.application import bp as application_bp
    from blueprints.admin import bp as admin_bp
    from blueprints.chat import bp as chat_bp
    from blueprints.notice import bp as notice_bp
    from blueprints.consumable import bp as consumable_bp
    from blueprints.notification import bp as notification_bp
    from blueprints.printer import bp as printer_bp
    from blueprints.app_release import bp as app_release_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(user_bp, url_prefix="/api/user")
    app.register_blueprint(application_bp, url_prefix="/api/application")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(chat_bp, url_prefix="/api/chat")
    app.register_blueprint(notice_bp, url_prefix="/api/notice")
    app.register_blueprint(consumable_bp, url_prefix="/api/consumable")
    app.register_blueprint(printer_bp, url_prefix="/api/printer")
    app.register_blueprint(notification_bp, url_prefix="/api/notification")
    app.register_blueprint(app_release_bp, url_prefix="/api/app")

    @app.route("/api/health")
    def health():
        """健康检查。"""
        return jsonify({"code": 0, "msg": "ok"})

    @app.route("/api/health/db")
    def health_db():
        """数据库诊断：连通性 + 表清单（部署排障用，无敏感信息）。"""
        try:
            from sqlalchemy import inspect, text
            with app.app_context():
                db.session.execute(text("SELECT 1"))
                tables = sorted(inspect(db.engine).get_table_names())
            required = {"users", "print_applications", "chat_messages", "announcements",
                        "consumables", "consumable_logs", "notifications"}
            missing = sorted(required - set(tables))
            return jsonify({"code": 0, "data": {"db": "ok", "missing_tables": missing}})
        except Exception as e:
            return jsonify({"code": 1, "msg": f"数据库连接失败: {str(e)[:200]}"}), 500

    @app.route("/api/lan")
    def lan():
        """本机局域网信息：前端据此生成手机扫码用的 HTTPS 地址二维码。"""
        https_on = os.path.isfile(app.config["SSL_CERT"]) and os.path.isfile(app.config["SSL_KEY"])
        return jsonify({
            "code": 0,
            "data": {
                "ips": _lan_ips(),
                "http_port": 5000,
                "https_port": app.config["HTTPS_PORT"],
                "https_enabled": https_on,
            },
        })

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def spa(path=""):
        """兜底服务前端构建产物（SPA），供单机 / 内网穿透直连 Flask 时使用。

        /api、/uploads 已由更具体的蓝图 / 路由命中，不会落到这里；
        走 Nginx 部署时前端由 Nginx 直接服务，本路由也不会被命中。
        """
        # 防御性排除 API 与上传前缀（避免未命中具体路由时返回 index.html）
        if path == "api" or path.startswith("api/") or path == "uploads" or path.startswith("uploads/"):
            return jsonify({"code": 404, "msg": "Not Found"}), 404
        # 命中具体静态文件（带 hash 的 js/css 等）则直接返回
        if path and os.path.isfile(os.path.join(FRONTEND_DIST, path)):
            resp = send_from_directory(FRONTEND_DIST, path)
            # 带 hash 的资源内容永不变化，浏览器可缓存一年（换版本时文件名必变）
            if path.replace("\\", "/").startswith("assets/"):
                resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return resp
        # 其余一律回退到 index.html（history 路由）
        index = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.isfile(index):
            resp = send_from_directory(FRONTEND_DIST, "index.html")
            # index 不缓存：发新版后用户强刷一次即可拿到新版本
            resp.headers["Cache-Control"] = "no-cache"
            return resp
        return jsonify({"code": 0, "msg": "前端尚未构建，请先执行 npm run build"})

    @app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        """开发环境直接提供上传文件访问。

        生产环境由 Nginx 的 location /uploads/ 拦截并直接读取磁盘，
        此路由不会被命中（仅作为本地联调时的兜底）。
        """
        return send_from_directory(app.config["UPLOAD_DIR"], filename)

    return app


app = create_app()


if __name__ == "__main__":
    # 仅用于本地开发；生产环境请用 gunicorn + Nginx。
    # 对外（内网穿透 / 公网）时必须关闭 debug：Werkzeug 交互式调试器若暴露公网可执行任意代码。
    # 故 debug 默认关闭，需要调试时设 FLASK_DEBUG=1。
    # debug 的自动重载(reloader)会 fork 子进程，多次启停易残留僵尸进程占住端口，
    # 默认同样关闭；需要自动重载时另设 FLASK_USE_RELOADER=1。
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    use_reloader = debug and os.getenv("FLASK_USE_RELOADER", "0") == "1"

    # 局域网 HTTPS（存在证书时自动启用）：手机浏览器要求安全上下文才允许调起摄像头
    if os.path.isfile(app.config["SSL_CERT"]) and os.path.isfile(app.config["SSL_KEY"]):
        _start_https(app)

    app.run(host="0.0.0.0", port=5000, debug=debug, use_reloader=use_reloader)
