# -*- coding: utf-8 -*-
"""把「Flask 主平台」和「sms-hub FastAPI」拼成一个 ASGI 应用，由 uvicorn 单进程托管。

为什么要反过来做（ASGI 托管 WSGI）而不是把 FastAPI 塞进 Flask：
  sms-hub 依赖 asyncio 的**长生命周期后台任务**（设备轮询、发送队列、保活、通知）。
  塞进 Flask（WSGI、同步、每请求一线程）后这些任务就没有常驻事件循环可用；
  反过来用 Starlette 的 WSGIMiddleware 把 Flask 包进去，事件循环只建一次，
  Flask 的同步视图由 Starlette 用线程池执行，两边都能正常工作。

路由分配（同一个端口 5000）：
  /hook/*      → sms-hub（ESP32 固件上报，认证在 /hook/{DEVICE_TOKEN}）
  其它          → Flask 主平台（网页、业务 API、静态资源）

sms-hub 的 /api/*（原来的收件箱/发送/设备管理接口）**不再对外暴露**：
主平台改用 services/native_sms.py 直接读 SQLite + 调内部发送函数，路由更少、鉴权统一。
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.middleware.wsgi import WSGIMiddleware
from starlette.routing import Mount

from vendor import sms_hub as smshub

log = logging.getLogger("smshub.bridge")

SMSHUB_PREFIX = "/smshub"


class HybridApp:
    """按路径把请求分给 sms-hub(FastAPI) 或 Flask(WSGI)。"""

    def __init__(self, flask_app, sms_app):
        self.sms_app = sms_app
        self.flask_asgi = WSGIMiddleware(flask_app)

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return  # lifespan 由外层 Starlette 统一处理
        path = scope.get("path", "") or ""

        if path == "/hook" or path.startswith("/hook/"):
            await self.sms_app(scope, receive, send)
            return

        await self.flask_asgi(scope, receive, send)


class HookOnlyApp:
    """给旧的 8025 端口用：只处理固件上报的 /hook/*，其余返回 404。

    这样 ESP32 固件里的 WEBHOOK_URL（http://IP:8025/hook/xxx）**完全不用改**；
    确认所有设备都改到 5000 端口后，把 SMSHUB_LEGACY_PORT 设为 0 即可关掉。
    """

    def __init__(self, sms_app):
        self.sms_app = sms_app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return
        path = scope.get("path", "") or ""
        if path == "/hook" or path.startswith("/hook/"):
            await self.sms_app(scope, receive, send)
            return
        body = b'{"ok":false,"detail":"this port only serves /hook/*"}'
        await send({"type": "http.response.start", "status": 404,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


def build_asgi(flask_app):
    """返回 (主 ASGI 应用, 仅 hook 的 ASGI 应用)。"""
    sms_app = smshub.get_app()

    @asynccontextmanager
    async def lifespan(_app):
        # 关键：在这里跑 sms-hub 的启动钩子（打开库、拉起设备轮询/发送队列/通知），
        # 并把事件循环登记给 Flask 线程使用（内嵌发短信靠它调度协程）。
        async with smshub.lifespan_context(sms_app):
            smshub.set_loop(asyncio.get_running_loop())
            log.info("sms-hub 内嵌启动完成（设备轮询 / 发送队列已就绪）")
            try:
                yield
            finally:
                log.info("sms-hub 内嵌关闭")

    main = Starlette(
        routes=[Mount("/", app=HybridApp(flask_app, sms_app))],
        lifespan=lifespan,
    )

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    legacy = Starlette(routes=[Mount("/", app=HookOnlyApp(sms_app))], lifespan=_noop_lifespan)
    return main, legacy
