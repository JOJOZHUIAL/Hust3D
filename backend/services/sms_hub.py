# -*- coding: utf-8 -*-
"""sms-hub 短信网关客户端（ESP32C3 + 4G 模组，局域网服务）。

替代原来那台装了 SmsForwarder 的手机：服务器把「手机号 + 正文」POST 给 sms-hub，
由 4G 模组真正发出去。协议（v2）：

  1) 取令牌：  POST {base}/api/login    {"user": "...", "password": "..."}  → {"token": "..."}
  2) 发短信：  POST {base}/api/send     {"sim_id": "...", "to": "13x...", "text": "..."}
                Header: Authorization: Bearer <token>
               → {"ok": true, "queued": true, "id": 12, "parts": 1, "sim_id": "...", "device_mac": "..."}
  3) 发信记录：GET  {base}/api/outbound?limit=20 → {"outbound": [{id, status, ...}]}

配置（.env）：
  SMSHUB_BASE_URL=http://192.168.1.150:8025
  SMSHUB_USER=admin
  SMSHUB_PASSWORD=********
  SMSHUB_SIM_ID=            # 留空则自动挑「已绑定在线设备」的那张卡
  SMSHUB_TIMEOUT=10
  SMSHUB_RETRIES=3

注意：`/hook/{token}` 是**设备上报**用的 webhook（ESP32 固件调 Hub），不是发短信接口，
不要拿它当发送地址（会 400/404）。
"""
import threading
import time

import requests
from flask import current_app

# 令牌缓存（进程内；401 时自动重新登录）
_token_lock = threading.Lock()
_token_cache = {"token": "", "base": "", "ts": 0.0}
_TOKEN_TTL = 6 * 3600  # 保守值：Hub 令牌默认 30 天，这里 6 小时刷新一次

# SIM 缓存
_sim_lock = threading.Lock()
_sim_cache = {"sim_id": "", "base": "", "ts": 0.0}
_SIM_TTL = 300


class SmsHubError(Exception):
    """sms-hub 调用失败。retryable=True 表示网络类问题，值得重试。"""

    def __init__(self, message, retryable=False, status=None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status


def _cfg():
    c = current_app.config
    return {
        "base": (c.get("SMSHUB_BASE_URL") or "").rstrip("/"),
        "user": c.get("SMSHUB_USER") or "admin",
        "password": c.get("SMSHUB_PASSWORD") or "",
        "sim_id": (c.get("SMSHUB_SIM_ID") or "").strip(),
        "timeout": float(c.get("SMSHUB_TIMEOUT") or 10),
        "retries": max(1, int(c.get("SMSHUB_RETRIES") or 3)),
    }


def configured():
    c = _cfg()
    return bool(c["base"] and c["password"])


def _login(cfg):
    """取（并缓存）Bearer 令牌。"""
    with _token_lock:
        fresh = (
            _token_cache["token"]
            and _token_cache["base"] == cfg["base"]
            and time.time() - _token_cache["ts"] < _TOKEN_TTL
        )
        if fresh:
            return _token_cache["token"]

        try:
            resp = requests.post(
                cfg["base"] + "/api/login",
                json={"user": cfg["user"], "password": cfg["password"]},
                timeout=cfg["timeout"],
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            raise SmsHubError(f"网关不可达（{type(e).__name__}）", retryable=True)
        except Exception as e:
            raise SmsHubError(f"登录请求失败：{type(e).__name__}: {str(e)[:80]}")

        if resp.status_code == 401:
            raise SmsHubError("sms-hub 账号或密码错误，请检查 SMSHUB_USER / SMSHUB_PASSWORD", status=401)
        if resp.status_code == 429:
            raise SmsHubError("sms-hub 登录尝试过于频繁，请稍后再试", retryable=True, status=429)
        if resp.status_code != 200:
            raise SmsHubError(f"sms-hub 登录失败 HTTP {resp.status_code}", status=resp.status_code)

        token = (resp.json() or {}).get("token") or ""
        if not token:
            raise SmsHubError("sms-hub 未返回令牌")
        _token_cache.update({"token": token, "base": cfg["base"], "ts": time.time()})
        return token


def _pick_sim(cfg, token):
    """挑一张可用的 SIM：优先「已绑定在线设备」的卡，其次任意启用卡。"""
    if cfg["sim_id"]:
        return cfg["sim_id"]
    with _sim_lock:
        if _sim_cache["sim_id"] and _sim_cache["base"] == cfg["base"] and \
                time.time() - _sim_cache["ts"] < _SIM_TTL:
            return _sim_cache["sim_id"]

    try:
        resp = requests.get(
            cfg["base"] + "/api/sims",
            headers={"Authorization": "Bearer " + token},
            timeout=cfg["timeout"],
        )
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        raise SmsHubError(f"网关不可达（{type(e).__name__}）", retryable=True)
    if resp.status_code != 200:
        raise SmsHubError(f"读取 SIM 列表失败 HTTP {resp.status_code}", status=resp.status_code)

    sims = (resp.json() or {}).get("sims") or []
    sims = [s for s in sims if s.get("enabled", True)]
    if not sims:
        raise SmsHubError("sms-hub 上没有启用的 SIM 卡")
    bound = [s for s in sims if s.get("current_device_mac")]
    sim_id = (bound or sims)[0].get("sim_id") or ""
    if not sim_id:
        raise SmsHubError("无法确定 SIM 卡，请在 .env 里设置 SMSHUB_SIM_ID")

    with _sim_lock:
        _sim_cache.update({"sim_id": sim_id, "base": cfg["base"], "ts": time.time()})
    return sim_id


def send_text(phone, text, retries=None):
    """发一条短信（带重试）。返回 {"ok": True, "id": ..., "sim_id": ..., "parts": ...}。

    失败抛 SmsHubError；retryable=True 的失败（网络抖动/5xx）会自动重试。
    """
    cfg = _cfg()
    if current_app.config.get("SMSHUB_EMBEDDED") and embedded_ready():
        return _send_embedded(cfg, phone, text)   # 进程内直接调，不走 HTTP

    if not configured():
        raise SmsHubError("未配置 sms-hub（SMSHUB_BASE_URL / SMSHUB_PASSWORD）")
    attempts = retries or cfg["retries"]
    last = None
    for i in range(attempts):
        try:
            return _send_once(cfg, phone, text)
        except SmsHubError as e:
            last = e
            if not e.retryable or i == attempts - 1:
                raise
            time.sleep(min(2 ** i, 8))  # 1s, 2s, 4s...
    raise last or SmsHubError("发送失败")


def _send_once(cfg, phone, text):
    token = _login(cfg)
    sim_id = _pick_sim(cfg, token)
    payload = {"sim_id": sim_id, "to": phone, "text": text}

    try:
        resp = requests.post(
            cfg["base"] + "/api/send",
            json=payload,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            timeout=cfg["timeout"],
        )
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        raise SmsHubError(f"网关不可达（{type(e).__name__}）", retryable=True)
    except Exception as e:
        raise SmsHubError(f"请求失败：{type(e).__name__}: {str(e)[:80]}")

    # 令牌过期 → 清缓存重试一次
    if resp.status_code == 401:
        with _token_lock:
            _token_cache.update({"token": "", "base": "", "ts": 0.0})
        raise SmsHubError("sms-hub 令牌失效，已重新登录将重试", retryable=True, status=401)

    if resp.status_code >= 500:
        raise SmsHubError(f"sms-hub 服务异常 HTTP {resp.status_code}", retryable=True,
                          status=resp.status_code)
    if resp.status_code != 200:
        detail = ""
        try:
            detail = (resp.json() or {}).get("detail") or ""
        except Exception:
            detail = (resp.text or "")[:80]
        raise SmsHubError(f"sms-hub 拒绝发送 HTTP {resp.status_code}：{detail}",
                          status=resp.status_code)

    data = resp.json() or {}
    if not data.get("ok"):
        raise SmsHubError(f"sms-hub 返回失败：{data}")
    return {
        "ok": True,
        "id": data.get("id"),
        "sim_id": data.get("sim_id") or sim_id,
        "parts": data.get("parts"),
        "device_mac": data.get("device_mac"),
    }


def send_3d_print_notification(phone_number, model_name, pickup_code=None, text=None):
    """【业务函数】3D 打印完成通知：给申请人发一条取件短信。

    参数：
      phone_number  接收人手机号（11 位）
      model_name    模型/文件名，用于正文
      pickup_code   取件号/申请编号（可选，会拼到正文里方便前台核对）
      text          需要完全自定义正文时传它（优先级最高）

    返回：{"ok": True, "id": ..., "sim_id": ..., "parts": ...}
    异常：SmsHubError（调用方决定是否入队重试）
    """
    phone = (phone_number or "").strip()
    if not phone:
        raise SmsHubError("手机号为空，未发送")

    body = (text or "").strip()
    if not body:
        name = (model_name or "打印件").strip()
        body = f"您好，您的3D打印件（{name}）已打印完成，请取件。"
        if pickup_code:
            body += f"取件号：{pickup_code}。"
    return send_text(phone, body)


def probe(timeout=3):
    """探测 sms-hub 是否可达（只请求 /api/health，不发短信）。"""
    cfg = _cfg()
    if not cfg["base"]:
        return False
    try:
        r = requests.get(cfg["base"] + "/api/health", timeout=timeout)
        return r.status_code == 200 and bool((r.json() or {}).get("ok"))
    except Exception:
        return False


# ---------------------------------------------------------------- 内嵌模式（进程内调用）

def embedded_ready():
    """内嵌的 sms-hub 是否已就绪（uvicorn 启动并跑完 lifespan）。"""
    try:
        from vendor import sms_hub as smshub
        return bool(smshub.get_loop()) and current_app.config.get("SMSHUB_EMBEDDED")
    except Exception:
        return False


async def _pick_sim_embedded(preferred=""):
    """内嵌模式挑卡：显式配置 > 已绑定设备的卡 > 唯一启用卡。"""
    from core.infra import db as hub_db

    if preferred:
        if await hub_db.get_sim(preferred):
            return preferred
        raise SmsHubError(f"配置的 SMSHUB_SIM_ID 不存在：{preferred}")

    sims = [s for s in await hub_db.list_sims() if s["enabled"]]
    if not sims:
        raise SmsHubError("sms-hub 上没有启用的 SIM 卡")
    bound = [s for s in sims if s["current_device_mac"]]
    if bound:
        return bound[0]["sim_id"]
    if len(sims) == 1:
        return sims[0]["sim_id"]
    raise SmsHubError("检测到多张 SIM 卡，请在 .env 里指定 SMSHUB_SIM_ID", retryable=False)


async def _enqueue_embedded(phone, text, preferred_sim=""):
    """真正在 sms-hub 的事件循环里执行的协程：解析 SIM → 入发送队列。"""
    from core.infra import db as hub_db
    from core.sms import sender

    sim_id = await _pick_sim_embedded(preferred_sim)
    sim = await hub_db.get_sim(sim_id)
    mac = sim["current_device_mac"] if sim else ""
    ob_id = await sender.enqueue_sms(phone, text, "platform", sim_id=sim_id, device_mac=mac)
    return {"ok": True, "id": ob_id, "sim_id": sim_id, "device_mac": mac}


def _send_embedded(cfg, phone, text):
    """从 Flask 线程同步调用内嵌 sms-hub（无 HTTP、无独立端口）。"""
    import asyncio

    from vendor import sms_hub as smshub

    loop = smshub.get_loop()
    if loop is None:
        raise SmsHubError("内嵌 sms-hub 尚未就绪", retryable=True)

    attempts = cfg["retries"]
    last = None
    for i in range(attempts):
        try:
            preferred = (current_app.config.get("SMSHUB_SIM_ID") or "").strip()
            fut = asyncio.run_coroutine_threadsafe(
                _enqueue_embedded(phone, text, preferred), loop
            )
            res = fut.result(timeout=cfg["timeout"] + 5)
            res.setdefault("parts", 1)
            return res
        except Exception as e:  # 跨线程异常原样抛出
            msg = f"{type(e).__name__}: {str(e)[:120]}"
            last = SmsHubError(f"内嵌发送失败：{msg}", retryable=True)
            if i < attempts - 1:
                time.sleep(min(2 ** i, 8))
    raise last
