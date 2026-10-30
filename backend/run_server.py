# -*- coding: utf-8 -*-
"""合并后的唯一启动入口：一个进程、一个事件循环，同时托管

  - Flask 主平台（3D 打印管理，业务 API / 网页）
  - sms-hub（短信网关：设备上报 /hook、收件箱/发送 API）
  - 可选：兼容端口（默认 8025），只服务 /hook/*，让没刷固件的 ESP32 继续工作

用法：
    python run_server.py            # 或 python app.py（app.py 在 SMSHUB_EMBEDDED=1 时会自动转到这）
环境变量（.env 亦可）：
    HOST=0.0.0.0
    PORT=5000
    SMSHUB_EMBEDDED=1
    SMSHUB_LEGACY_PORT=8025         # 0 = 不开兼容端口
"""
import asyncio
import os
import socket
import sys

import uvicorn


def _port_in_use(port, timeout=0.4):
    """端口是否已被监听（用连接探测，比 bind 判定在 Windows 上更可靠）。"""
    if not port:
        return False
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _print_port_busy(port):
    print("", flush=True)
    print("=" * 66, flush=True)
    print(f"[错误] 端口 {port} 已被占用，服务没能启动。", flush=True)
    print("       最常见原因：上一个后端进程没关干净（覆盖文件后又开了一个）。", flush=True)
    print("", flush=True)
    print("  处理办法：", flush=True)
    print(f"    1) 看谁占用：netstat -ano | findstr :{port}", flush=True)
    print("    2) 任务管理器 → 详细信息 → 结束所有 python.exe", flush=True)
    print("    3) 重新双击 启动服务器.bat", flush=True)
    print("=" * 66, flush=True)


def _harden_event_loop_policy():
    """Windows 上默认的 ProactorEventLoop 对 aiosqlite/多路复用更稳，保持默认即可；
    这里只确保 Python 3.8+ 的 asyncio 默认策略不被旧代码改动。"""
    if sys.platform.startswith("win"):
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass


async def _serve_all(main_app, legacy_app, host, port, legacy_port):
    servers = []

    main_cfg = uvicorn.Config(
        main_app, host=host, port=port, log_level="info",
        access_log=False, lifespan="on",
    )
    servers.append(uvicorn.Server(main_cfg))

    if legacy_app is not None and legacy_port:
        legacy_cfg = uvicorn.Config(
            legacy_app, host=host, port=legacy_port, log_level="warning",
            access_log=False, lifespan="on",
        )
        servers.append(uvicorn.Server(legacy_cfg))

    tasks = [asyncio.create_task(s.serve(), name=f"uvicorn-{s.config.port}") for s in servers]
    print(f"[boot] 主服务 :{port}（Flask 主平台 + sms-hub /hook）", flush=True)
    if legacy_port:
        print(f"[boot] 兼容端口 :{legacy_port}（仅 /hook/*，给未刷固件的 ESP32 用）", flush=True)
    try:
        # return_exceptions=True：兼容端口被占用（比如旧的独立 sms-hub 还在跑）时，
        # 只记录告警，绝不让主服务跟着退出。
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for s, res in zip(servers, results):
            if isinstance(res, BaseException):
                if s.config.port == legacy_port:
                    print(f"[boot][warn] 兼容端口 {legacy_port} 启动失败（多半是被占用）：{res}", flush=True)
                    print(f"[boot][warn] 主服务不受影响，仍可通过 :{port}/hook 接收设备上报", flush=True)
                else:
                    raise res
    finally:
        for s in servers:
            s.should_exit = True


def main(flask_app=None, host=None, port=None, legacy_port=None):
    _harden_event_loop_policy()

    if flask_app is None:
        from app import app as flask_app  # 延迟导入，避免循环

    port = int(port or os.getenv("PORT", "5000"))
    host = host or os.getenv("HOST", "0.0.0.0")
    if legacy_port is None:
        legacy_port = int(os.getenv("SMSHUB_LEGACY_PORT", "8025"))

    # 关键：sms-hub 的 config.py 在 import 时读取环境变量，必须先灌进去
    from vendor import sms_hub as _hub
    _hub.apply_config_from_platform(flask_app.config)

    # 启动前先探测端口：被占用时给出明确提示，而不是甩一屏 traceback
    if _port_in_use(port):
        _print_port_busy(port)
        raise SystemExit(1)
    if legacy_port and _port_in_use(legacy_port):
        print(f"[boot][warn] 兼容端口 {legacy_port} 已被占用，本次跳过它"
              f"（设备可改报 :{port}/hook，或先结束占用进程）", flush=True)
        legacy_port = 0

    from smshub_asgi import build_asgi

    main_app, legacy_app = build_asgi(flask_app)
    try:
        asyncio.run(_serve_all(main_app, legacy_app, host, port, legacy_port))
    except (OSError, SystemExit) as e:
        # 端口被占用是最常见的启动失败，这里给中文提示，避免甩一大段 traceback
        msg = str(e)
        if "10048" in msg or "address already in use" in msg.lower() or "only be used once" in msg:
            print("", flush=True)
            print("=" * 62, flush=True)
            print(f"[错误] 端口 {port} 已被占用，服务没能启动。", flush=True)
            print("       多半是上一个后端进程没关干净（覆盖文件后直接又开了一个）。", flush=True)
            print("", flush=True)
            print("  处理办法（任选）：", flush=True)
            print(f"    1) 查看谁占用：netstat -ano | findstr :{port}", flush=True)
            print("    2) 任务管理器 → 详细信息 → 结束所有 python.exe", flush=True)
            print("    3) 然后重新双击 启动服务器.bat", flush=True)
            print("=" * 62, flush=True)
        else:
            print(f"[错误] 服务启动失败：{e!r}", flush=True)
            print(f"       若提示端口相关，请执行：netstat -ano | findstr :{port}", flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
