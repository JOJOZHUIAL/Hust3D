# -*- coding: utf-8 -*-
"""sms-hub（ESP32C3 + ML307R 4G 短信网关）以「内嵌模块」方式并入主平台。

来源：https://github.com/chenxuuu/sms-hub （MIT，见同目录 LICENSE）
原始目录结构：core/ 后端（FastAPI）、web/ 前端（React+Vite）、firmware/ 固件。

这里没有改它的任何业务代码，只做三件适配：
  1. 把 vendor/sms_hub 加入 sys.path，让它内部的 `from core.xxx import ...` 能正常导入；
  2. 提供一个「只构建 App、不自己起 uvicorn」的入口（原 core/main.py 在 __main__ 里启动）；
  3. 把它的配置映射到主平台的 .env（见 ENV_MAP），并暴露异步事件循环，供 Flask 线程
     直接调用发送函数（真正的「函数调用」而不是 HTTP）。

注意：**不再包含 React 前端** —— 界面由主平台的 Vue 页面重写，数据由
services/native_sms.py 直接读 SQLite，sms-hub 只负责与 4G 模组通信（/hook + 发送队列）。

主平台只需要 `import vendor.sms_hub as smshub; smshub.get_app()`。
"""
import os
import sys
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parent
if str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))

# 主平台 .env → sms-hub 环境变量 的映射（都不写死在代码里）
ENV_MAP = {
    "SMSHUB_DEVICE_TOKEN": "DEVICE_TOKEN",   # 固件 /hook/{token} 里的 token
    "SMSHUB_USER": "WEBUI_USER",
    "SMSHUB_PASSWORD": "WEBUI_PASS",
    "SMSHUB_JWT_SECRET": "JWT_SECRET",
    "SMSHUB_DATA_DIR": "DATA_DIR",
    "SMSHUB_LISTEN_PORT": "LISTEN_PORT",
}

_app = None
_loop = None  # uvicorn 的事件循环，Flask 线程通过它调度协程


def apply_config_from_platform(flask_config):
    """把主平台 Flask 配置里以 SMSHUB_ 开头的项灌进环境变量（供 sms-hub 读取）。

    注意：必须在 import core.* 之前调用，因为它的 config.py 在导入时求值。
    """
    for target, source in ENV_MAP.items():
        val = flask_config.get(target)
        if val is None or val == "":
            continue
        os.environ.setdefault(source, str(val))
    # 数据目录（库 + .jwt_secret）默认放主平台 backend/instance/smshub，别污染源码树
    if not os.getenv("DATA_DIR"):
        # backend/vendor/sms_hub → backend/instance/smshub
        backend_dir = os.path.dirname(os.path.dirname(VENDOR_DIR))
        data_dir = os.path.join(backend_dir, "instance", "smshub")
        os.makedirs(data_dir, exist_ok=True)
        os.environ["DATA_DIR"] = data_dir
    # 前端已废弃（改由主平台 Vue 页面），给 sms-hub 一个真实存在的空目录，
    # 免得它每次启动都警告"前端构建产物不存在"。
    empty_web = VENDOR_DIR / "__no_web__"
    empty_web.mkdir(parents=True, exist_ok=True)
    os.environ["WEB_DIST"] = str(empty_web)


def get_app():
    """构建并缓存 sms-hub 的 FastAPI 应用（带 lifespan/后台任务，但不起服务）。"""
    global _app
    if _app is not None:
        return _app

    from core import main as hub_main  # noqa: E402  （导入即完成路由注册）

    _app = hub_main.app
    return _app


def lifespan_context(app):
    """拿 sms-hub 的 lifespan（打开 DB、启动设备轮询/发送队列/通知线程）。"""
    return app.router.lifespan_context(app)


def set_loop(loop):
    """uvicorn 启动后把事件循环登记进来，供 Flask 线程线程安全地调度协程。"""
    global _loop
    _loop = loop


def get_loop():
    return _loop
