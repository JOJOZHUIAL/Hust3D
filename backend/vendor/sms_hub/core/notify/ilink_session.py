"""微信 ClawBot 会话:单用户绑定 + context_token 刷新 + 失效清理。

会话态存 kv ``ilink_sess:{channel_id}``,与 notify_channels 分离避免 UI 保存竞态。
后台 worker 长轮询 getupdates;首次入站自动绑定 to_user_id;不做命令解析。
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time

from core.infra import config
from core.infra import db
from core.notify import ilink

log = logging.getLogger("ilink_session")

AUTH_FAIL_LIMIT = 3
_auth_fails: dict[str, int] = {}


def sess_key(channel_id: str) -> str:
    return f"ilink_sess:{channel_id}"


async def load_session(channel_id: str) -> dict:
    raw = await db.get_kv(sess_key(channel_id), "")
    if not raw:
        return {}
    with contextlib.suppress(Exception):
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    return {}


async def save_session(channel_id: str, data: dict) -> None:
    await db.set_kv(sess_key(channel_id), json.dumps(data, ensure_ascii=False))


async def clear_session(channel_id: str) -> None:
    await db.set_kv(sess_key(channel_id), "{}")
    _auth_fails.pop(channel_id, None)


def find_channel(channel_id: str) -> dict | None:
    for ch in config.NOTIFY_CHANNELS:
        if ch.get("id") == channel_id and ch.get("type") == "wechat_clawbot":
            return ch
    return None


def enabled_channels() -> list[dict]:
    out = []
    for ch in config.NOTIFY_CHANNELS:
        if ch.get("type") != "wechat_clawbot" or not ch.get("enabled"):
            continue
        token = str((ch.get("config") or {}).get("bot_token") or "").strip()
        if token:
            out.append(ch)
    return out


async def patch_channel_config(channel_id: str, patch: dict) -> dict | None:
    """合并写通道 config → apply_overrides → 持久化 kv cfg。返回更新后的通道。"""
    raw = await db.get_kv("cfg", "{}")
    cur: dict = {}
    with contextlib.suppress(Exception):
        cur = json.loads(raw or "{}") or {}
    channels = list(cur.get("notify_channels") or config.NOTIFY_CHANNELS)
    found = False
    for i, ch in enumerate(channels):
        if str(ch.get("id", "")) != channel_id:
            continue
        if str(ch.get("type", "")) != "wechat_clawbot":
            continue
        cfg = dict(ch.get("config") or {})
        for k, v in patch.items():
            if v is None:
                cfg.pop(k, None)
            else:
                cfg[k] = v
        channels[i] = {**ch, "config": cfg}
        found = True
        break
    if not found:
        # 回退:内存中有通道但尚未写入 cfg(首次保存前)——以内存为准补进 cfg
        mem = find_channel(channel_id)
        if not mem:
            return None
        cfg = dict(mem.get("config") or {})
        for k, v in patch.items():
            if v is None:
                cfg.pop(k, None)
            else:
                cfg[k] = v
        channels.append({**mem, "config": cfg})
    cur["notify_channels"] = channels
    config.apply_overrides(cur)
    await db.set_kv("cfg", json.dumps(cur, ensure_ascii=False))
    return find_channel(channel_id)


async def apply_login(
    channel_id: str,
    *,
    bot_token: str,
    ilink_bot_id: str = "",
    base_url: str = "",
) -> dict | None:
    """扫码确认后写入 token/Bot ID/base_url,并清空旧 session。"""
    patch = {
        "bot_token": bot_token,
        "ilink_bot_id": str(ilink_bot_id or "").strip() or ilink.bot_id_from_token(bot_token),
        "base_url": (base_url or ilink.DEFAULT_BASE_URL).rstrip("/"),
    }
    await clear_session(channel_id)
    ch = await patch_channel_config(channel_id, patch)
    _auth_fails.pop(channel_id, None)
    return ch


async def logout(channel_id: str, *, clear_bind: bool = True) -> None:
    """退出登录:清 token/session,可选清 to_user_id。"""
    patch: dict = {"bot_token": "", "ilink_bot_id": "", "base_url": ""}
    if clear_bind:
        patch["to_user_id"] = ""
    await patch_channel_config(channel_id, patch)
    await clear_session(channel_id)


async def bind_status(channel_id: str) -> dict:
    ch = find_channel(channel_id)
    cfg = (ch or {}).get("config") or {}
    sess = await load_session(channel_id)
    token = str(cfg.get("bot_token") or "").strip()
    bot_id = str(cfg.get("ilink_bot_id") or "").strip() or ilink.bot_id_from_token(token)
    to_uid = str(cfg.get("to_user_id") or "").strip()
    return {
        "channel_id": channel_id,
        "logged_in": bool(token),
        "to_user_id": to_uid,
        "session_ready": bool(token and bot_id and to_uid),
        "last_inbound_at": sess.get("last_inbound_at") or "",
        "last_error": sess.get("last_error") or "",
    }


async def _mark_auth_fail(channel_id: str, err: str) -> None:
    n = _auth_fails.get(channel_id, 0) + 1
    _auth_fails[channel_id] = n
    sess = await load_session(channel_id)
    sess["last_error"] = err[:300]
    await save_session(channel_id, sess)
    if n >= AUTH_FAIL_LIMIT:
        log.warning("微信通道 %s 连续鉴权失败 %d 次,清空登录态", channel_id, n)
        await logout(channel_id, clear_bind=False)


async def _handle_inbound(channel: dict, msg: dict) -> None:
    cid = channel["id"]
    cfg = channel.get("config") or {}
    to_uid = str(cfg.get("to_user_id") or "").strip()
    from_uid = msg["from_user_id"]
    ctx = msg["context_token"]

    if not to_uid:
        # 首次入站自动绑定
        await patch_channel_config(cid, {"to_user_id": from_uid})
        to_uid = from_uid
        log.info("微信通道 %s 已绑定用户 %s", cid, from_uid)
    elif from_uid != to_uid:
        log.debug("微信通道 %s 忽略非绑定用户 %s", cid, from_uid)
        return

    sess = await load_session(cid)
    sess["context_token"] = ctx
    sess["last_inbound_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    sess["last_error"] = ""
    await save_session(cid, sess)
    _auth_fails[cid] = 0


async def _poll_one(channel: dict) -> bool:
    """拉一轮 getupdates。返回 True=正常完成(长轮询 hold/业务已处理),
    False=该轮未正常完成(网络错误等),供 worker 决定是否退避。"""
    cid = channel["id"]
    cfg = channel.get("config") or {}
    token = str(cfg.get("bot_token") or "").strip()
    base_url = str(cfg.get("base_url") or "").strip() or ilink.DEFAULT_BASE_URL
    if not token:
        return False
    sess = await load_session(cid)
    buf = str(sess.get("get_updates_buf") or "")
    try:
        data = await ilink.getupdates(token, buf, base_url=base_url)
    except ilink.ILinkError as e:
        if e.ret == ilink.STALE_SYNC_RET:
            sess = await load_session(cid)
            sess.pop("get_updates_buf", None)
            sess["last_error"] = ""
            await save_session(cid, sess)
            log.info("微信通道 %s 同步游标已失效,已自动重置", cid)
        elif e.auth:
            await _mark_auth_fail(cid, str(e))
        else:
            sess = await load_session(cid)
            sess["last_error"] = str(e)[:300]
            await save_session(cid, sess)
            log.debug("微信 getupdates %s: %s", cid, e)
        return False
    except Exception as e:
        log.warning("微信 getupdates 异常 %s: %s", cid, e)
        return False

    new_buf = data.get("get_updates_buf")
    if new_buf:
        sess = await load_session(cid)
        sess["get_updates_buf"] = str(new_buf)
        await save_session(cid, sess)

    # 通道可能在等待期间被改过,重新取最新
    channel = find_channel(cid) or channel
    for msg in ilink.extract_user_text_messages(data.get("msgs")):
        await _handle_inbound(channel, msg)
        channel = find_channel(cid) or channel

    _auth_fails[cid] = 0
    return True


async def worker():
    """长轮询刷新会话;未配置通道时挂起。"""
    announced = False
    backoff = 0
    while True:
        channels = enabled_channels()
        if not channels:
            if not announced:
                log.info("微信 ClawBot 未启用或未登录,会话轮询挂起")
                announced = True
            await asyncio.sleep(10)
            continue
        if announced:
            log.info("微信 ClawBot 会话轮询启动(%d 通道)", len(channels))
            announced = False
        try:
            results = await asyncio.gather(
                *[_poll_one(ch) for ch in channels], return_exceptions=True
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("微信会话轮询异常")
            results = [False] * len(channels)
        # 全部正常(长轮询 hold)→ 恢复立即节奏;有失败 → 指数退避。
        # 修复前错误路径无条件 0.2s 重试,外部端点不可达时 ~5 req/s
        # 热循环打 getupdates,可能被限流/拉黑。退避 2s→4s→…→60s 封顶。
        if results and all(r is True for r in results):
            backoff = 0
            await asyncio.sleep(0.2)
        else:
            backoff = min(backoff + 1, 5)
            await asyncio.sleep(min(2.0 * (2 ** (backoff - 1)), 60.0))
