"""从环境变量读取配置。所有变量见仓库根目录 .env.example。"""
import os
import secrets
from pathlib import Path
from copy import deepcopy

from core.sms import phone

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "sms.db"

# 设备 token(与固件 config.h 的 API_TOKEN 一致)。
# 设备地址无需配置:设备会通过 webhook 上报自己的 IP,hub 学习并持久化。
# DEVICE_URL 可选,仅作为初始提示/webhook 不可用时的手工兜底。
DEVICE_URL = os.getenv("DEVICE_URL", "").rstrip("/")
DEVICE_TOKEN = os.getenv("DEVICE_TOKEN", "").strip() or (
    DEVICE_URL.rsplit("/", 1)[-1] if DEVICE_URL else ""
)

# 日志级别(默认 INFO;排障设 DEBUG)。应用与 uvicorn 共用,见 infra/logging_setup.py。
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
ALERT_CONSECUTIVE_FAILS = int(os.getenv("ALERT_CONSECUTIVE_FAILS", "3"))

# v2 多设备:全局共享 DEVICE_TOKEN,每台瘦终端用 MAC 区分。
# POLL_INTERVAL 仍是每设备 poll 循环的兜底等待(生产默认 300s,§7.2;demo 可设 5s)。
# 跨设备并发 I/O 池上限(§7.2),超出排队;单设备内部仍串行化。
MAX_DEVICE_IO_CONCURRENCY = max(1, int(os.getenv("MAX_DEVICE_IO_CONCURRENCY", "4")))
# 在线判定下限(§7.2):heartbeat 与 data-plane 各自的新鲜度地板值(秒)。
# 在线判定下限(§7.2):heartbeat 与 data-plane 新鲜度地板。生产用默认;
# demo 可经 env 调小以快速观察离线切换(不影响生产默认值)。
HEARTBEAT_ONLINE_FLOOR_S = int(os.getenv("HEARTBEAT_ONLINE_FLOOR_S", "150"))
DATA_PLANE_ONLINE_FLOOR_S = int(os.getenv("DATA_PLANE_ONLINE_FLOOR_S", "630"))
# Hub 自身监听地址集合(SSRF 防护用),lifespan 启动时探测填充。
HUB_SELF_ADDRS: set[str] = set()
# 开发逃生:demo 栈 Hub 与 mock 同机时放行 loopback 设备地址。生产保持关闭。
ALLOW_LOOPBACK_DEVICE = os.getenv("ALLOW_LOOPBACK_DEVICE", "").strip().lower() in (
    "1", "true", "yes", "on"
)
# 管理员代发默认发送卡片(全局唯一,§9);未配置/不可用时管理员代发直接失败。
DEFAULT_SEND_SIM_ID = os.getenv("DEFAULT_SEND_SIM_ID", "").strip()

TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
TG_API_BASE = os.getenv("TG_API_BASE", "https://api.telegram.org").rstrip("/")
TG_ENABLED = bool(TG_BOT_TOKEN and TG_CHAT_ID)
TG_MANAGE_ENABLED = os.getenv("TG_MANAGE_ENABLED", "1") not in ("0", "false", "no")

FORWARD_SMS_TO = phone.canonicalize(os.getenv("FORWARD_SMS_TO", ""))
ADMIN_PHONE = phone.canonicalize(os.getenv("ADMIN_PHONE", ""))
# 黑名单:逗号分隔,支持完整号码与前缀(1069 即前缀)
BLACKLIST = [x.strip() for x in os.getenv("BLACKLIST", "").split(",") if x.strip()]

# 保号:每 N 天发起一次极小流量(0=禁用)
KEEPALIVE_INTERVAL_DAYS = float(os.getenv("KEEPALIVE_INTERVAL_DAYS", "0"))
KEEPALIVE_PING_HOST = os.getenv("KEEPALIVE_PING_HOST", "119.29.29.29")
TOMBSTONE_KEEP_DAYS = int(os.getenv("TOMBSTONE_KEEP_DAYS", "30"))
MESSAGE_KEEP_DAYS = int(os.getenv("MESSAGE_KEEP_DAYS", "0"))

# 选择性推送(按规则决定每条消息发往哪些通道;关/空=全发,见 notify/push_rules.py)
PUSH_RULES_ENABLED = os.getenv("PUSH_RULES_ENABLED", "").strip().lower() in (
    "1", "true", "yes", "on"
)
PUSH_RULES: list[dict] = []

# 保号动作:ping(蜂窝流量,默认)/sms(发短信给 KEEPALIVE_TARGET)
KEEPALIVE_ACTION = os.getenv("KEEPALIVE_ACTION", "ping").strip().lower() or "ping"
KEEPALIVE_TARGET = os.getenv("KEEPALIVE_TARGET", "").strip()

# 定时心跳通知:每天 HEARTBEAT_NOTIFY_HOUR 点向所有启用通道发一条存活汇报
HEARTBEAT_NOTIFY_ENABLED = os.getenv("HEARTBEAT_NOTIFY_ENABLED", "").strip().lower() in (
    "1", "true", "yes", "on"
)
HEARTBEAT_NOTIFY_HOUR = max(0, min(23, int(os.getenv("HEARTBEAT_NOTIFY_HOUR", "9"))))

# 通知队列上限:notify_jobs(pending+retry)超此数时驱逐 attempts 最大者,防止爆库
NOTIFY_QUEUE_MAX = max(50, int(os.getenv("NOTIFY_QUEUE_MAX", "500")))

WEBUI_USER = os.getenv("WEBUI_USER", "admin")
_DEFAULT_PASS = "admin123"
WEBUI_PASS = os.getenv("WEBUI_PASS", _DEFAULT_PASS)
IS_DEFAULT_PASS = WEBUI_PASS == _DEFAULT_PASS

LISTEN_PORT = int(os.getenv("LISTEN_PORT", "8025"))

# 登录令牌签名密钥:未配置时生成一个并落盘,重启后会话依然有效
_secret_file = DATA_DIR / ".jwt_secret"
JWT_SECRET = os.getenv("JWT_SECRET", "")
if not JWT_SECRET:
    if _secret_file.exists():
        JWT_SECRET = _secret_file.read_text().strip()
    else:
        JWT_SECRET = secrets.token_hex(32)
        _secret_file.write_text(JWT_SECRET)
        _secret_file.chmod(0o600)

TOKEN_TTL_S = 30 * 86400  # 登录有效期 30 天


def _channel_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in ("0", "false", "no", "off", "")


def _normalize_channel(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        # 防御非法类型(如 dict/str 混入 notify_channels 列表),否则迭代出
        # 非 dict 元素时 .get 抛 AttributeError → 导入/保存路径 500
        return None
    typ = str(raw.get("type", "")).strip()
    if typ not in ("telegram", "sms_forward", "webhook_json", "webhook_get",
                   "dingtalk", "feishu", "bark", "pushplus", "serverchan", "gotify",
                   "email", "wechat_clawbot"):
        return None
    cid = str(raw.get("id") or typ).strip()
    if not cid:
        cid = typ
    cfg = dict(raw.get("config") or {})
    out = {
        "id": cid,
        "type": typ,
        "name": str(raw.get("name") or cid).strip() or cid,
        "enabled": _channel_bool(raw.get("enabled", False)),
        "config": {},
    }
    if typ == "telegram":
        token = str(cfg.get("bot_token", "")).strip()
        chat_id = str(cfg.get("chat_id", "")).strip()
        api_base = str(cfg.get("api_base", "")).strip().rstrip("/") or "https://api.telegram.org"
        out["config"] = {"bot_token": token, "chat_id": chat_id, "api_base": api_base}
    elif typ == "sms_forward":
        out["config"] = {"to": phone.canonicalize(cfg.get("to", ""))}
    elif typ in ("webhook_json", "webhook_get"):
        out["config"] = {"url": str(cfg.get("url", "")).strip()}
    elif typ in ("dingtalk", "feishu"):
        # 加签机器人:webhook url + 加签 secret(可选,留空则不加签)。
        out["config"] = {
            "url": str(cfg.get("url", "")).strip(),
            "secret": str(cfg.get("secret", "")).strip(),
        }
    elif typ == "bark":
        out["config"] = {"url": str(cfg.get("url", "")).strip()}
    elif typ == "pushplus":
        out["config"] = {
            "token": str(cfg.get("token", "")).strip(),
            "channel": str(cfg.get("channel", "")).strip(),
        }
    elif typ == "serverchan":
        out["config"] = {"sendkey": str(cfg.get("sendkey", "")).strip()}
    elif typ == "gotify":
        out["config"] = {
            "url": str(cfg.get("url", "")).strip().rstrip("/"),
            "token": str(cfg.get("token", "")).strip(),
        }
    elif typ == "email":
        try:
            port = int(cfg.get("smtp_port") or 465)
        except (TypeError, ValueError):
            port = 465
        out["config"] = {
            "smtp_host": str(cfg.get("smtp_host", "")).strip(),
            "smtp_port": port,
            "smtp_username": str(cfg.get("smtp_username", "")).strip(),
            "smtp_password": str(cfg.get("smtp_password", "")).strip(),
            "from": str(cfg.get("from", "")).strip(),
            "to": str(cfg.get("to", "")).strip(),
        }
    elif typ == "wechat_clawbot":
        # bot_token/Bot ID 来自扫码登录;to_user_id 首次入站自动绑定或手填。
        base = str(cfg.get("base_url", "")).strip().rstrip("/")
        out["config"] = {
            "bot_token": str(cfg.get("bot_token", "")).strip(),
            "ilink_bot_id": str(cfg.get("ilink_bot_id", "")).strip(),
            "base_url": base,
            "to_user_id": str(cfg.get("to_user_id", "")).strip(),
        }
    # 推送文案模板(占位符 {sender} {code} {text} 等);各类型统一保留,
    # 是否使用由 notifier 渲染层决定(webhook_get 不用——其 config.url 本身即模板)。
    out["config"]["template"] = str(cfg.get("template") or "").strip()
    return out


def _normalize_rule(raw: dict) -> dict | None:
    """规整一条选择性推送规则。非法 match_type / 缺 id → 丢弃。"""
    if not isinstance(raw, dict):
        return None
    typ = str(raw.get("match_type", "")).strip().lower()
    if typ not in ("sender", "keyword", "code_present", "sim_id", "all"):
        return None
    rid = str(raw.get("id") or "").strip()
    if not rid:
        return None
    cids = raw.get("channel_ids") or []
    if not isinstance(cids, list):
        cids = [str(cids)]
    cids = [str(x).strip() for x in cids if str(x).strip()]
    seen: set[str] = set()
    cids = [x for x in cids if not (x in seen or seen.add(x))]
    try:
        priority = int(raw.get("priority", 100))
    except (TypeError, ValueError):
        priority = 100
    return {
        "id": rid,
        "name": str(raw.get("name") or rid).strip() or rid,
        "enabled": _channel_bool(raw.get("enabled", True)),
        "priority": priority,
        "match_type": typ,
        "match_value": str(raw.get("match_value") or ""),
        "sim_id": str(raw.get("sim_id") or "").strip() or None,
        "drop": bool(raw.get("drop", False)),
        "channel_ids": cids,
    }


def _default_notify_channels() -> list[dict]:
    channels = [
        {
            "id": "telegram",
            "type": "telegram",
            "name": "Telegram",
            "enabled": bool(TG_BOT_TOKEN and TG_CHAT_ID),
            "config": {
                "bot_token": TG_BOT_TOKEN,
                "chat_id": TG_CHAT_ID,
                "api_base": TG_API_BASE,
            },
        },
        {
            "id": "sms_forward",
            "type": "sms_forward",
            "name": "短信转发",
            "enabled": bool(FORWARD_SMS_TO),
            "config": {"to": FORWARD_SMS_TO},
        },
        {
            "id": "webhook_json",
            "type": "webhook_json",
            "name": "POST JSON",
            "enabled": False,
            "config": {"url": ""},
        },
        {
            "id": "webhook_get",
            "type": "webhook_get",
            "name": "GET 请求",
            "enabled": False,
            "config": {"url": ""},
        },
        {
            "id": "dingtalk",
            "type": "dingtalk",
            "name": "钉钉机器人",
            "enabled": False,
            "config": {"url": "", "secret": ""},
        },
        {
            "id": "feishu",
            "type": "feishu",
            "name": "飞书机器人",
            "enabled": False,
            "config": {"url": "", "secret": ""},
        },
    ]
    return [c for c in (_normalize_channel(ch) for ch in channels) if c]


NOTIFY_CHANNELS = _default_notify_channels()


# ── 运行时可改配置 ──
# 以上 env 值只是初始默认;下列键可在 Web UI 修改,存 kv("cfg"),即时生效。
def _recompute():
    global TG_ENABLED, TG_BOT_TOKEN, TG_CHAT_ID, TG_API_BASE, FORWARD_SMS_TO
    tg = next((c for c in NOTIFY_CHANNELS if c["type"] == "telegram"), None)
    if tg:
        TG_BOT_TOKEN = str(tg["config"].get("bot_token", "")).strip()
        TG_CHAT_ID = str(tg["config"].get("chat_id", "")).strip()
        TG_API_BASE = str(tg["config"].get("api_base", "https://api.telegram.org")).strip().rstrip("/")
    else:
        TG_BOT_TOKEN = ""
        TG_CHAT_ID = ""
        TG_API_BASE = "https://api.telegram.org"
    fwd = next((c for c in NOTIFY_CHANNELS if c["type"] == "sms_forward"), None)
    if fwd:
        FORWARD_SMS_TO = phone.canonicalize(fwd["config"].get("to", ""))
    else:
        FORWARD_SMS_TO = ""
    TG_ENABLED = bool(TG_BOT_TOKEN and TG_CHAT_ID and (tg or {}).get("enabled", True))


def apply_overrides(d: dict):
    """把 kv 里保存的覆盖值应用到模块属性(启动时与每次保存后调用)。"""
    global ADMIN_PHONE, BLACKLIST
    global POLL_INTERVAL, ALERT_CONSECUTIVE_FAILS
    global KEEPALIVE_INTERVAL_DAYS, KEEPALIVE_PING_HOST
    global TG_MANAGE_ENABLED
    global TOMBSTONE_KEEP_DAYS
    global MESSAGE_KEEP_DAYS
    global NOTIFY_CHANNELS
    global DEFAULT_SEND_SIM_ID
    global PUSH_RULES_ENABLED, PUSH_RULES
    global KEEPALIVE_ACTION, KEEPALIVE_TARGET
    global HEARTBEAT_NOTIFY_ENABLED, HEARTBEAT_NOTIFY_HOUR
    global NOTIFY_QUEUE_MAX

    if "notify_channels" in d:
        channels = []
        for raw in d.get("notify_channels") or []:
            ch = _normalize_channel(raw)
            if ch:
                channels.append(ch)
        if channels:
            NOTIFY_CHANNELS = channels
    if "tg_manage_enabled" in d:
        TG_MANAGE_ENABLED = bool(d["tg_manage_enabled"])
    if "admin_phone" in d:
        ADMIN_PHONE = phone.canonicalize(d["admin_phone"])
    if "blacklist" in d:
        BLACKLIST = [x.strip() for x in str(d["blacklist"]).split(",") if x.strip()]
    if "poll_interval" in d:
        POLL_INTERVAL = max(5, int(d["poll_interval"]))
    if "alert_consecutive_fails" in d:
        ALERT_CONSECUTIVE_FAILS = max(1, int(d["alert_consecutive_fails"]))
    if "keepalive_interval_days" in d:
        try:
            v = float(d["keepalive_interval_days"])
        except (TypeError, ValueError):
            v = 0.0
        # 0=禁用;否则 clamp 到 1~3650 天(防误配导致每小时反复发短信/USSD/跑流量)
        KEEPALIVE_INTERVAL_DAYS = 0.0 if v <= 0 else max(1.0, min(3650.0, v))
    if "keepalive_ping_host" in d and str(d["keepalive_ping_host"]).strip():
        KEEPALIVE_PING_HOST = str(d["keepalive_ping_host"]).strip()
    if "tombstone_keep_days" in d:
        TOMBSTONE_KEEP_DAYS = max(1, int(d["tombstone_keep_days"]))
    if "message_keep_days" in d:
        MESSAGE_KEEP_DAYS = max(0, int(d["message_keep_days"]))
    if "default_send_sim_id" in d:
        DEFAULT_SEND_SIM_ID = str(d["default_send_sim_id"]).strip()
    if "push_rules_enabled" in d:
        PUSH_RULES_ENABLED = bool(d["push_rules_enabled"])
    if "notify_rules" in d:
        rules = []
        for raw in d.get("notify_rules") or []:
            r = _normalize_rule(raw)
            if r:
                rules.append(r)
        PUSH_RULES = rules
    if "keepalive_action" in d:
        KEEPALIVE_ACTION = str(d["keepalive_action"]).strip().lower() or "ping"
    if "keepalive_target" in d:
        KEEPALIVE_TARGET = str(d["keepalive_target"]).strip()
    if "heartbeat_notify_enabled" in d:
        HEARTBEAT_NOTIFY_ENABLED = bool(d["heartbeat_notify_enabled"])
    if "heartbeat_notify_hour" in d:
        HEARTBEAT_NOTIFY_HOUR = max(0, min(23, int(d["heartbeat_notify_hour"])))
    if "notify_queue_max" in d:
        NOTIFY_QUEUE_MAX = max(50, int(d["notify_queue_max"]))
    _recompute()


def sanitized_notify_channels() -> list[dict]:
    out = []
    for ch in NOTIFY_CHANNELS:
        item = deepcopy(ch)
        if item["type"] == "telegram":
            token = item["config"].get("bot_token", "")
            item["config"]["bot_token"] = ""
            item["config"]["bot_token_set"] = bool(token)
        elif item["type"] in ("dingtalk", "feishu"):
            secret = item["config"].get("secret", "")
            item["config"]["secret"] = ""
            item["config"]["secret_set"] = bool(secret)
        elif item["type"] == "email":
            pwd = item["config"].get("smtp_password", "")
            item["config"]["smtp_password"] = ""
            item["config"]["smtp_password_set"] = bool(pwd)
        elif item["type"] == "pushplus":
            token = item["config"].get("token", "")
            item["config"]["token"] = ""
            item["config"]["token_set"] = bool(token)
        elif item["type"] == "serverchan":
            key = item["config"].get("sendkey", "")
            item["config"]["sendkey"] = ""
            item["config"]["sendkey_set"] = bool(key)
        elif item["type"] == "gotify":
            token = item["config"].get("token", "")
            item["config"]["token"] = ""
            item["config"]["token_set"] = bool(token)
        elif item["type"] == "wechat_clawbot":
            token = item["config"].get("bot_token", "")
            item["config"]["bot_token"] = ""
            item["config"]["bot_token_set"] = bool(token)
        out.append(item)
    return out
