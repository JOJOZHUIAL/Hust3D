# -*- coding: utf-8 -*-
"""原生短信模块（极简）：直接读写 sms-hub 的 SQLite 库 + 复用其发送队列。

设计取舍（相比之前的 sms-hub 全套 API）：
  - **读**：绕开 sms-hub 的 FastAPI 查询层，直接 SELECT messages / devices / sims 三张表，
    只取页面要用的字段，不需要先登录换 token、不需要理解它的分页/过滤语义；
  - **写（发送）**：不自己拼 HTTP，也不碰它的路由，直接调用 `sms_hub.send_text()`
    （内嵌模式下就是 to_thread → asyncio → sender.enqueue_sms，进程内零拷贝）；
  - **状态**：设备在线看 last_hook_ts/last_poll_ok_ts，信号看 last_status_json 里的 modem 快照，
    都是纯读，不打扰后台轮询任务。

只读连接用 sqlite3 普通模式（WAL 下读写可并发），只执行 SELECT，不写库。
"""
import json
import re
import sqlite3
import threading
import time
from datetime import datetime

import requests
from flask import current_app

# 从短信正文里提取验证码（4~8 位数字，避开年份/长串）
CODE_RE = re.compile(r"(?<!\d)(\d{4,8})(?!\d)")


# ---------------------------------------------------------------- 连接与位置

def db_path():
    """sms-hub 的 SQLite 路径（与内嵌模块的 DATA_DIR 保持一致）。"""
    cfg = current_app.config
    data_dir = (cfg.get("SMSHUB_DATA_DIR") or "").strip()
    if not data_dir:
        import os
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(backend_dir, "instance", "smshub")
    import os
    return os.path.join(data_dir, "sms.db")


def _connect():
    path = db_path()
    conn = sqlite3.connect(path, timeout=4)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(sql, params=()):
    try:
        conn = _connect()
    except Exception:
        return []
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except Exception:
        return []
    finally:
        conn.close()


# ---------------------------------------------------------------- 状态

def _online_threshold(device):
    hb = device.get("heartbeat_interval_s") or 60
    return max(90, int(hb) * 3)


def status():
    """设备在线 / 信号 / SIM 号码 —— 页面顶部状态卡只要这三样。"""
    devices = _rows("SELECT * FROM devices WHERE enabled=1 ORDER BY last_hook_ts DESC")
    sims = {s["sim_id"]: s for s in _rows("SELECT * FROM sims")}
    now = time.time()

    device = devices[0] if devices else None
    online = False
    # 自动识别接入的卡：绑定在（在线）设备上的算「在用」，其余列为「备用/未接入」
    bound_mac = (device or {}).get("mac") or ""
    ts_now = time.time()
    sim_cards = []
    for s in sims.values():
        if not s.get("enabled"):
            continue
        bound = bool(s.get("current_device_mac")) and s["current_device_mac"] == bound_mac
        sim_cards.append({
            "sim_id": s["sim_id"],
            "number": _pretty_msisdn(s.get("msisdn") or "") or "未上报",
            "operator": _operator_text(s.get("operator")),
            "online": bound,
            "bound": bound,
        })
    sim_cards.sort(key=lambda x: (not x["bound"], x["number"]))
    last_seen = None
    signal = None
    operator = ""
    sim_number = ""

    if device:
        ts = max(device.get("last_hook_ts") or 0, device.get("last_poll_ok_ts") or 0)
        last_seen = ts or None
        online = bool(ts) and (now - ts) < _online_threshold(device)

        modem = {}
        try:
            raw = device.get("last_status_json") or "{}"
            modem = (json.loads(raw) or {}).get("modem") or {}
        except Exception:
            modem = {}
        # csq_dbm 是 dBm（负数），换成人看懂的 0~4 格
        csq = modem.get("csq_dbm")
        if isinstance(csq, (int, float)):
            signal = _signal_bars(float(csq))
        sim = sims.get(device.get("current_sim_id") or "") or {}
        operator = modem.get("operator") or sim.get("operator") or ""
        sim_number = (sim.get("msisdn") or modem.get("msisdn") or "")
        if not sim_number:
            others = [s.get("msisdn") for s in sims.values()
                      if s.get("enabled") and s.get("msisdn")]
            sim_number = others[0] if others else ""
        sim_number = _pretty_msisdn(sim_number)

    detail = {}
    sync = {}
    counters = {}
    if device:
        try:
            detail = json.loads(device.get("last_status_json") or "{}") or {}
        except Exception:
            detail = {}
        buf = detail.get("buffer") or {}
        dev_counters = detail.get("counters") or {}
        sync = {
            "cursor": device.get("cursor"),
            "device_latest": detail.get("latest_id"),
            "buffer_used": buf.get("count"),
            "buffer_capacity": buf.get("capacity") or 50,
            "dropped": buf.get("dropped_total") or 0,
            "last_poll": _ago(device.get("last_poll_ok_ts")),
            "last_hook": _ago(device.get("last_hook_ts")),
            "local_received": message_count(),
            "local_sent": _count("outbound"),
        }
        counters = {
            "rx": dev_counters.get("rx_total"),
            "tx": dev_counters.get("tx_total"),
            "webhook_fail": dev_counters.get("webhook_fail_total"),
        }

    return {
        "online": online,
        "signal": signal,              # 0~4，None=未知
        "signal_text": _signal_text(signal),
        "operator": operator,
        "sim_number": sim_number or "未上报",
        "device": (device or {}).get("mac"),
        "last_seen": _ago(last_seen),
        "sim_count": len([s for s in sims.values() if s.get("enabled")]),
        "sims": sim_cards,
        # 设备自报的详细状态（信号/IMEI/网络/WiFi/固件…）
        "detail": {
            "mac": detail.get("mac") or (device or {}).get("mac"),
            "ip": detail.get("ip"),
            "fw": detail.get("fw"),
            "uptime": _duration(detail.get("uptime_s")),
            "free_heap_kb": round((detail.get("free_heap") or 0) / 1024) if detail.get("free_heap") else None,
            "wifi_ssid": detail.get("wifi_ssid"),
            "wifi_rssi": detail.get("wifi_rssi"),
            "reset_reason": detail.get("reset_reason"),
            "last_error": detail.get("last_error"),
            "modem": _modem_view((detail.get("modem") or {})),
        },
        "sync": sync,
        "counters": counters,
    }


# 运营商识别：设备上报的字段五花八门（英文全称、缩写、MCC/MNC 数字码、中文、带空格/点号），
# 统一归一化后映射到三大运营商；认不出的原样显示。
_OP_MOBILE = ("CHINA MOBILE", "CHINAMOBILE", "CMCC", "CHN-CM", "CHNCM", "CM", "MOBILE",
              "中国移动", "移动", "46000", "46002", "46004", "46007", "46008", "46020")
_OP_UNICOM = ("CHINA UNICOM", "CHINAUNICOM", "UNICOM", "CU", "CHN-CU", "CHNCU", "CUCC",
              "中国联通", "联通", "46001", "46006", "46009", "46010")
_OP_TELECOM = ("CHINA TELECOM", "CHINATELECOM", "TELECOM", "CT", "CHN-CT", "CHNCT", "CTC",
               "中国电信", "电信", "46003", "46005", "46011", "46012")
_OP_BROADNET = ("CHINA BROADNET", "BROADNET", "BROADCOM", "中国广电", "广电", "46015")
_OP_ALIAS = {}
for _names, _cn in ((_OP_MOBILE, "中国移动"), (_OP_UNICOM, "中国联通"),
                    (_OP_TELECOM, "中国电信"), (_OP_BROADNET, "中国广电")):
    for _n in _names:
        _OP_ALIAS[_n] = _cn


def _normalize_op(op):
    """归一化：去空格/点号/下划线/连字符，统一大写。"""
    raw = str(op or "").strip().upper()
    for ch in (" ", ".", "_", "-", "/", "|"):
        raw = raw.replace(ch, "")
    return raw


def _operator_text(op):
    """设备上报的运营商 → 中文名（认不出则原样返回，不再一律显示「未知」）。"""
    if op is None:
        return "未知"
    raw = str(op).strip()
    if not raw:
        return "未知"

    norm = _normalize_op(raw)
    if norm in _OP_ALIAS:
        return _OP_ALIAS[norm]
    # 子串兜底：如 "CHINA MOBILE(46000)" / "CMCC 4G" / "中国移动通信"
    for key, cn in _OP_ALIAS.items():
        if len(key) >= 4 and key in norm:  # 太短的缩写（CM/CU/CT）不做子串匹配，避免误判
            return cn
    # 已经是中文运营商名（含“移动/联通/电信/广电”）→ 规范化
    for cn in ("中国移动", "中国联通", "中国电信", "中国广电"):
        if cn[2:] in raw:
            return cn
    return raw  # 认不出的原样显示，便于排查


def _pretty_msisdn(raw):
    """把 +8613362648430 变成 133 6264 8430 这种好读的形式。"""
    s = (raw or "").strip()
    if s.startswith("+86"):
        s = s[3:]
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) == 11:
        return f"{digits[:3]} {digits[3:7]} {digits[7:]}"
    return s or ""


def _signal_bars(dbm):
    """dBm → 0~4 格（-60 以上满格）。"""
    if dbm >= -65:
        return 4
    if dbm >= -80:
        return 3
    if dbm >= -95:
        return 2
    if dbm >= -110:
        return 1
    return 0


def _signal_text(bars):
    return {0: "无信号", 1: "弱", 2: "一般", 3: "良好", 4: "很强"}.get(bars, "未知") if bars is not None else "未知"


def _count(table):
    row = _rows(f"SELECT COUNT(*) AS n FROM {table}")
    return row[0]["n"] if row else 0


def _duration(sec):
    try:
        sec = int(sec or 0)
    except (TypeError, ValueError):
        return ""
    if sec < 60:
        return f"{sec} 秒"
    if sec < 3600:
        return f"{sec // 60} 分 {sec % 60} 秒"
    return f"{sec // 3600} 小时 {sec % 3600 // 60} 分"


CEREQ_TEXT = {0: "未注册", 1: "已注册", 2: "搜索中", 3: "注册被拒", 4: "未知", 5: "漫游"}


def _modem_view(m):
    """把设备上报的 modem 对象翻译成页面直接能显示的中文。"""
    csq = m.get("csq_dbm")
    ber = m.get("ber")
    return {
        "model": m.get("model") or "",
        "sim": bool(m.get("sim")),
        "registered": CEREQ_TEXT.get(m.get("cereg"), "未知"),
        "signal_dbm": csq,
        "signal_bars": _signal_bars(csq) if isinstance(csq, (int, float)) else None,
        "signal_text": _signal_text(_signal_bars(csq)) if isinstance(csq, (int, float)) else "未知",
        "rsrp": m.get("rsrp_dbm"),
        "rsrq": m.get("rsrq_db"),
        "ber": "—" if ber in (None, -1) else ber,
        "operator": _operator_text(m.get("operator")),
        "imsi_tail": m.get("imsi_tail"),
        "iccid_tail": m.get("iccid_tail"),
        "apn": m.get("apn"),
        "data": bool(m.get("data_connection_active")),
        "sms_rx_ok": bool(m.get("sms_rx_config_ok")),
    }


def _ago(ts):
    if not ts:
        return "从未"
    delta = int(time.time() - ts)
    if delta < 60:
        return f"{delta} 秒前"
    if delta < 3600:
        return f"{delta // 60} 分钟前"
    if delta < 86400:
        return f"{delta // 3600} 小时前"
    return f"{delta // 86400} 天前"


# ---------------------------------------------------------------- 固件日志 / 强制拉取

def _call_loop(coro, timeout=10):
    """把协程丢到内嵌 sms-hub 的事件循环里执行（Flask 是同步的）。"""
    import asyncio

    from vendor import sms_hub as smshub

    loop = smshub.get_loop()
    if loop is None:
        raise RuntimeError("内嵌 sms-hub 未就绪")
    return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=timeout)


async def _fetch_log(since):
    from core.device import manager as device_manager

    mgr = device_manager.get()
    for rt in mgr.runtimes.values():
        if rt.base_url:
            return await rt.fetch_log(int(since or 0))
    return {"seq": 0, "lines": []}


def device_log(since=0, limit=200):
    """拉取固件日志（增量）。失败返回空列表 + 原因，不影响页面。"""
    try:
        data = _call_loop(_fetch_log(since))
    except Exception as e:
        return {"lines": [], "seq": since, "error": f"{type(e).__name__}: {str(e)[:80]}"}
    lines = (data or {}).get("lines") or []
    lines = lines[-int(limit):]
    return {
        "lines": [{"seq": x.get("seq"), "text": x.get("text")} for x in lines],
        "seq": (data or {}).get("seq") or since,
    }


async def _pull_now():
    from core.device import manager as device_manager
    from core.device import poller

    mgr = device_manager.get()
    got = 0
    for mac, rt in mgr.runtimes.items():
        if not rt.base_url:
            continue
        try:
            got += await poller.poll_device(mgr, rt)
        except Exception:
            continue
    return {"ok": True, "new_messages": got}


def pull_now():
    """强制让设备立刻上报一次（等价旧 UI 的「强制拉取」）。"""
    try:
        return _call_loop(_pull_now(), timeout=15)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:100]}"}


# ---------------------------------------------------------------- 收件箱

def _norm_phone(raw):
    """号码归一：只留数字，去掉 86/+86 前缀，取后 11 位（用于跨源匹配姓名）。"""
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(digits) > 11 and digits.startswith("86"):
        digits = digits[2:]
    if len(digits) > 11:
        digits = digits[-11:]
    return digits


def _alias_map(phones):
    """号码 → 发件人姓名/备注。

    匹配顺序：1) sms-hub 的 contacts.alias；2) 主平台 users 里的学生姓名。
    号码统一归一化（去掉 +86 / 空格），避免 `+8613800138000` 和 `13800138000` 匹配不上。
    """
    out = {}
    if not phones:
        return out

    # ① 联系人别名（按归一化后的号码比对）
    for r in _rows("SELECT phone, alias FROM contacts"):
        if r.get("alias"):
            out[_norm_phone(r["phone"])] = r["alias"]

    # ② 平台用户姓名（sms 里常带 +86 前缀，这里用后 11 位匹配）
    try:
        from models import User

        rows = User.query.filter(User.phone.isnot(None)).all()
        for u in rows:
            key = _norm_phone(u.phone)
            if key and u.name and key not in out:
                out[key] = u.name
    except Exception:
        pass

    # 映射回原始 sender 字符串
    return {p: out.get(_norm_phone(p), "") for p in phones}


def messages(limit=50, before_id=None, keyword=None):
    """按时间倒序返回收到的短信；带「备注」，并支持按 联系人/内容/备注 搜索。"""
    limit = max(1, min(int(limit or 50), 200))
    sql = ("SELECT id, sender, text, received_at, sim_id, content_type, blocked "
           "FROM messages")
    where, params = [], []
    if before_id:
        where.append("id < ?")
        params.append(int(before_id))
    if keyword:
        kw = f"%{keyword}%"
        where.append("(text LIKE ? OR sender LIKE ?)")
        params.extend([kw, kw])
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    rows = _rows(sql, tuple(params))
    aliases = _alias_map(sorted({r.get("sender") for r in rows if r.get("sender")}))

    items = []
    for r in rows:
        text = r.get("text") or ""
        sender = r.get("sender") or "未知"
        item = {
            "id": r["id"],
            "sender": sender,
            "alias": aliases.get(sender, ""),
            "text": text,
            "time": r.get("received_at") or "",
            "code": extract_code(text),
            "blocked": bool(r.get("blocked")),
            "mms": (r.get("content_type") or "sms") != "sms",
        }
        items.append(item)

    # 备注命中也要能搜到（备注来自两张表，只能在内存里再筛一遍）
    if keyword:
        kw = keyword.lower()
        items = [i for i in items
                 if kw in (i["sender"] or "").lower()
                 or kw in (i["text"] or "").lower()
                 or kw in (i["alias"] or "").lower()]
    return items


def extract_code(text):
    """挑一个最像验证码的 4~8 位数字（优先 6 位、靠前出现的）。"""
    if not text:
        return ""
    cands = CODE_RE.findall(text)
    if not cands:
        return ""
    cands.sort(key=lambda c: (abs(len(c) - 6), text.index(c)))
    return cands[0]


def outbound(limit=50, before_id=None):
    """发送记录（sms-hub 的 outbound 表，按时间倒序）。"""
    limit = max(1, min(int(limit or 50), 200))
    sql = "SELECT id, to_phone, text, status, parts, attempts, last_error, created_at FROM outbound"
    where, params = [], []
    if before_id:
        where.append("id < ?")
        params.append(int(before_id))
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = _rows(sql, tuple(params))
    return [{
        "id": r["id"],
        "phone": r.get("to_phone") or "",
        "text": r.get("text") or "",
        "status": r.get("status") or "",
        "status_text": {"sent": "已发送", "pending": "发送中", "give_up": "失败"}.get(
            r.get("status"), r.get("status") or ""),
        "time": r.get("created_at") or "",
        "error": r.get("last_error") or "",
        "attempts": r.get("attempts") or 0,
    } for r in rows]


def message_count():
    row = _rows("SELECT COUNT(*) AS n FROM messages")
    return (row[0]["n"] if row else 0)


# ---------------------------------------------------------------- 发送

def send(phone, text):
    """调用内嵌/HTTP 的 sms-hub 发送（复用既有队列与重试）。"""
    from services import sms_hub

    phone = (phone or "").strip()
    text = (text or "").strip()
    if not re.fullmatch(r"1\d{10}", phone):
        raise ValueError("手机号格式不正确")
    if not text:
        raise ValueError("短信内容不能为空")
    if len(text) > 500:
        raise ValueError("短信内容过长（最多 500 字）")
    return sms_hub.send_text(phone, text)

# ---------------------------------------------------------------- 自动通知开关

AUTO_KEYS = {
    "auto_sms": ("NOTIFY_AUTO_SMS", "短信"),
    "auto_email": ("NOTIFY_AUTO_EMAIL", "邮件"),
}


def auto_flags():
    """两个自动通知开关（打印完成时是否自动发短信 / 发邮件）。"""
    cfg = current_app.config
    return {
        "auto_sms": bool(cfg.get("NOTIFY_AUTO_SMS", True)),
        "auto_email": bool(cfg.get("NOTIFY_AUTO_EMAIL", True)),
    }


def save_auto_flags(auto_sms=None, auto_email=None):
    """保存开关到 .env 并立即生效（不重启）。"""
    from utils.env_file import set_var

    cfg = current_app.config
    if auto_sms is not None:
        cfg["NOTIFY_AUTO_SMS"] = bool(auto_sms)
        set_var("NOTIFY_AUTO_SMS", "1" if auto_sms else "0")
    if auto_email is not None:
        cfg["NOTIFY_AUTO_EMAIL"] = bool(auto_email)
        set_var("NOTIFY_AUTO_EMAIL", "1" if auto_email else "0")
    return auto_flags()
