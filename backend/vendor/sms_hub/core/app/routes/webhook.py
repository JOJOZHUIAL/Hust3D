"""Device webhook routes (v2)。

POST /hook/{token}:token 只认证不区分设备;body 必须带 mac。Hub 只做
token 校验、MAC/IMSI 规范化、状态快照保存和异步拉取排队,**不在请求内同步
执行设备 pull**(§6.2)。响应 {ok, pull_scheduled}。
"""
import json
import logging
import secrets

from fastapi import APIRouter, HTTPException, Request

from core.infra import config
from core.device import manager as device_manager
from core.device.manager import WebhookError

log = logging.getLogger("hub")
router = APIRouter()


@router.post("/hook/{token}")
async def hook(token: str, request: Request):
    try:
        ok = bool(config.DEVICE_TOKEN) and secrets.compare_digest(
            token, config.DEVICE_TOKEN
        )
    except TypeError:
        # compare_digest 对非 ASCII 抛 TypeError:按 token 不匹配处理(404),
        # 否则任意非 ASCII path 段会让 /hook/* 直接 500
        ok = False
    if not ok:
        raise HTTPException(status_code=404)
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}
        parse_error = "请求体不是合法 JSON"
    else:
        parse_error = None if isinstance(body, dict) else "请求体必须是 JSON 对象"
    peer = request.client.host if request.client else ""
    try:
        if parse_error:
            raise WebhookError(parse_error)
        return await device_manager.get().handle_webhook(body, peer)
    except WebhookError as e:
        # 只记诊断用字段(mac/event/ip/port);webhook body 可能携带 modem.imsi
        # (boot/hello/heartbeat),按"完整 IMSI 不入日志"铁律绝不整包打印。
        safe = ({k: body.get(k) for k in ("mac", "event", "ip", "port") if k in body}
                if isinstance(body, dict) else {})
        log.warning("webhook 拒绝(400):%s | 字段=%s(来自 %s)", e, safe, peer)
        raise HTTPException(status_code=400, detail=str(e))
