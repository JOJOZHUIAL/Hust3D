"""微信 ClawBot / iLink HTTP 客户端(薄封装,无第三方 SDK)。

协议入口: https://ilinkai.weixin.qq.com
鉴权:扫码登录拿到 bot_token 后,后续请求带 Bearer + AuthorizationType。
主动发送文本需携带 Bot ID 与每条消息唯一的 client_id;context_token 留空。
"""
from __future__ import annotations

import base64
import logging
import secrets
import uuid
from typing import Any

import httpx

log = logging.getLogger("ilink")

DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
CHANNEL_VERSION = "1.0.2"
BOT_TYPE = 3
MESSAGE_TYPE_USER = 1
MESSAGE_TYPE_BOT = 2
MESSAGE_STATE_NORMAL = 2
ITEM_TYPE_TEXT = 1
STALE_SYNC_RET = -14


class ILinkError(RuntimeError):
    """iLink 业务或传输错误。"""

    def __init__(self, message: str, *, ret: int | None = None, auth: bool = False):
        super().__init__(message)
        self.ret = ret
        self.auth = auth


def _random_wechat_uin() -> str:
    """X-WECHAT-UIN:随机 uint32 → 十进制字符串 → base64。"""
    n = secrets.randbits(32)
    return base64.b64encode(str(n).encode("utf-8")).decode("ascii")


def _auth_headers(bot_token: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {bot_token}",
        "X-WECHAT-UIN": _random_wechat_uin(),
    }


def _minimal_headers() -> dict[str, str]:
    return {"Content-Type": "application/json"}


def _base_info() -> dict[str, str]:
    return {"channel_version": CHANNEL_VERSION}


def bot_id_from_token(bot_token: str) -> str:
    """兼容旧配置:部分 iLink token 的冒号前缀即 ``ilink_bot_id``。"""
    candidate = str(bot_token or "").strip().split(":", 1)[0].strip()
    return candidate if candidate.endswith("@im.bot") else ""


def new_client_id() -> str:
    """生成 iLink 用于消息去重/关联的唯一客户端消息 ID。"""
    return str(uuid.uuid4())


def _check_ret(data: dict, *, path: str) -> None:
    for field in ("ret", "errcode"):
        ret = data.get(field)
        if ret in (None, "", 0, "0"):
            continue
        try:
            ret_i = int(ret)
        except (TypeError, ValueError) as e:
            raise ILinkError(f"iLink {path} {field}={ret}") from e
        # 常见鉴权失败码区间不公开,把明确未授权文案与常见非 0 一并标 auth
        errmsg = str(data.get("errmsg") or data.get("err_msg") or data.get("msg") or "")
        low = errmsg.lower()
        auth = (
            ret_i in (-1, 401, 403)
            or "token" in low
            or "auth" in low
            or "login" in low
        )
        raise ILinkError(
            f"iLink {path} {field}={ret_i} {errmsg}".strip(),
            ret=ret_i,
            auth=auth,
        )


async def get_bot_qrcode(*, base_url: str = DEFAULT_BASE_URL,
                        bot_type: int = BOT_TYPE) -> dict[str, Any]:
    """获取登录二维码。返回含 qrcode(轮询用)与 qrcode_img_content(展示用)。"""
    url = f"{base_url.rstrip('/')}/ilink/bot/get_bot_qrcode"
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(url, params={"bot_type": bot_type}, headers=_minimal_headers())
        r.raise_for_status()
        data = r.json()
    if not isinstance(data, dict):
        raise ILinkError("get_bot_qrcode 响应非 JSON 对象")
    if not data.get("qrcode"):
        raise ILinkError("get_bot_qrcode 未返回 qrcode")
    return data


async def get_qrcode_status(qrcode: str, *, base_url: str = DEFAULT_BASE_URL) -> dict[str, Any]:
    """长轮询扫码状态(服务端可 hold ~35s)。confirmed 时含 bot_token/baseurl。"""
    url = f"{base_url.rstrip('/')}/ilink/bot/get_qrcode_status"
    async with httpx.AsyncClient(timeout=40.0) as c:
        r = await c.get(url, params={"qrcode": qrcode}, headers=_minimal_headers())
        r.raise_for_status()
        data = r.json()
    if not isinstance(data, dict):
        raise ILinkError("get_qrcode_status 响应非 JSON 对象")
    return data


async def getupdates(
    bot_token: str,
    get_updates_buf: str = "",
    *,
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = 40.0,
) -> dict[str, Any]:
    """长轮询拉取入站消息。"""
    url = f"{base_url.rstrip('/')}/ilink/bot/getupdates"
    body = {"get_updates_buf": get_updates_buf or "", "base_info": _base_info()}
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(url, json=body, headers=_auth_headers(bot_token))
    except httpx.HTTPError as e:
        raise ILinkError(f"getupdates 网络错误: {e}") from e
    if r.status_code in (401, 403):
        raise ILinkError(f"getupdates HTTP {r.status_code}", auth=True)
    if r.is_error:
        raise ILinkError(f"getupdates HTTP {r.status_code}: {(r.text or '')[:200]}")
    data = r.json()
    if not isinstance(data, dict):
        raise ILinkError("getupdates 响应非 JSON 对象")
    _check_ret(data, path="getupdates")
    return data


async def send_text(
    bot_token: str,
    *,
    from_user_id: str = "",
    to_user_id: str,
    text: str,
    context_token: str = "",
    client_id: str = "",
    base_url: str = DEFAULT_BASE_URL,
) -> dict[str, Any]:
    """向已绑定用户发送文本;主动推送时 ``context_token`` 应为空。"""
    from_uid = str(from_user_id or "").strip() or bot_id_from_token(bot_token)
    to_uid = str(to_user_id or "").strip()
    msg_client_id = str(client_id or "").strip() or new_client_id()
    if not from_uid or not to_uid:
        raise ILinkError("缺少 from_user_id 或 to_user_id")
    url = f"{base_url.rstrip('/')}/ilink/bot/sendmessage"
    body = {
        "msg": {
            "from_user_id": from_uid,
            "to_user_id": to_uid,
            "client_id": msg_client_id,
            "message_type": MESSAGE_TYPE_BOT,
            "message_state": MESSAGE_STATE_NORMAL,
            "context_token": str(context_token or ""),
            "item_list": [
                {"type": ITEM_TYPE_TEXT, "text_item": {"text": text or ""}},
            ],
        },
        "base_info": _base_info(),
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.post(url, json=body, headers=_auth_headers(bot_token))
    except httpx.HTTPError as e:
        raise ILinkError(f"sendmessage 网络错误: {e}") from e
    if r.status_code in (401, 403):
        raise ILinkError(f"sendmessage HTTP {r.status_code}", auth=True)
    if r.is_error:
        raise ILinkError(f"sendmessage HTTP {r.status_code}: {(r.text or '')[:200]}")
    # iLink 成功时可能返回空 body;HTTP 2xx 即上游已接受。
    data = r.json() if (r.text or "").strip() else {}
    if not isinstance(data, dict):
        raise ILinkError("sendmessage 响应非 JSON 对象")
    _check_ret(data, path="sendmessage")
    return data


def extract_user_text_messages(msgs: list | None) -> list[dict[str, Any]]:
    """从 getupdates.msgs 提取用户文本消息:{from_user_id, context_token, text}。"""
    out: list[dict[str, Any]] = []
    for msg in msgs or []:
        if not isinstance(msg, dict):
            continue
        if int(msg.get("message_type") or 0) != MESSAGE_TYPE_USER:
            continue
        from_uid = str(msg.get("from_user_id") or "").strip()
        ctx = str(msg.get("context_token") or "").strip()
        if not from_uid or not ctx:
            continue
        text = ""
        for item in msg.get("item_list") or []:
            if not isinstance(item, dict):
                continue
            if int(item.get("type") or 0) == ITEM_TYPE_TEXT:
                ti = item.get("text_item") or {}
                text = str((ti or {}).get("text") or "")
                break
        out.append({
            "from_user_id": from_uid,
            "context_token": ctx,
            "text": text,
        })
    return out
