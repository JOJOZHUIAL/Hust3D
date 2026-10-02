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
        db.create_all()

    # 注册蓝图（此处 import 避免循环依赖）
    from blueprints.auth import bp as auth_bp
    from blueprints.user import bp as user_bp
    from blueprints.application import bp as application_bp
    from blueprints.admin import bp as admin_bp
    from blueprints.chat import bp as chat_bp
    from blueprints.notice import bp as notice_bp
    from blueprints.consumable import bp as consumable_bp
    from blueprints.notification import bp as notification_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(user_bp, url_prefix="/api/user")
    app.register_blueprint(application_bp, url_prefix="/api/application")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(chat_bp, url_prefix="/api/chat")
    app.register_blueprint(notice_bp, url_prefix="/api/notice")
    app.register_blueprint(consumable_bp, url_prefix="/api/consumable")
    app.register_blueprint(notification_bp, url_prefix="/api/notification")

    @app.route("/api/health")
    def health():
        """健康检查。"""
        return jsonify({"code": 0, "msg": "ok"})

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
            return send_from_directory(FRONTEND_DIST, path)
        # 其余一律回退到 index.html（history 路由）
        index = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.isfile(index):
            return send_from_directory(FRONTEND_DIST, "index.html")
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
