# -*- coding: utf-8 -*-
"""拓竹（Bambu Lab）打印机状态监视服务。

拓竹打印机在局域网内自带 MQTT broker（8883 端口，TLS，用户名 bblp，密码为访问码）。
本服务为每台打印机维护一条后台连接，订阅 device/+/report，
把最新状态（进度/剩余时间/温度/状态机）缓存到内存供接口轮询。

线程全部 daemon 化，随进程退出自动结束。
"""
import json
import ssl
import threading
from datetime import datetime

import paho.mqtt.client as mqtt

from extensions import db
from models import Printer

# Flask 应用引用（sync_with_db 时注入，供后台线程补 app context）
_app = None

# printer_id -> mqtt client（运行中）
_clients = {}
# printer_id -> 最新状态快照
_snapshots = {}
_lock = threading.Lock()

STATE_TEXT = {
    "IDLE": "空闲",
    "RUNNING": "打印中",
    "PAUSE": "已暂停",
    "PAUSED": "已暂停",
    "FINISH": "打印完成",
    "FAILED": "打印失败",
    "PREPARE": "准备中",
    "SLICING": "切片中",
    "SLICE": "切片中",
}


def snapshot_for(printer):
    """返回某台打印机的状态快照（无连接/离线时返回离线骨架）。"""
    snap = _snapshots.get(printer.id)
    base = {
        "id": printer.id,
        "name": printer.name,
        "ip": printer.ip,
        "serial": printer.serial or (snap or {}).get("serial"),
        "online": False,
        "state": None,
        "state_text": "离线",
        "percent": None,
        "remaining_time": None,
        "task_name": None,
        "gcode_file": None,
        "print_file": None,
        "nozzle_temp": None,
        "bed_temp": None,
        "chamber_temp": None,
        "updated_at": None,
    }
    if snap:
        base.update(snap)
        base["online"] = True
    return base


def _clean_print_file(gcode_file):
    """从打印文件路径提取干净名称：去目录、去 .gcode.3mf/.3mf/.gcode 后缀。"""
    if not gcode_file:
        return None
    name = str(gcode_file).replace("\\", "/").split("/")[-1].strip()
    low = name.lower()
    for suf in (".gcode.3mf", ".3mf", ".gcode"):
        if low.endswith(suf):
            name = name[: -len(suf)]
            break
    return name or None


def _fmt_state(gcode_state):
    if not gcode_state:
        return None
    return STATE_TEXT.get(gcode_state.upper(), gcode_state)


def _on_connect(client, userdata, flags, reason_code, properties):
    client.subscribe("device/+/report", qos=0)


def _on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8", "ignore"))
    except Exception:
        return
    parts = msg.topic.split("/")
    if len(parts) < 3 or parts[0] != "device" or parts[2] != "report":
        return
    serial = parts[1]
    info = payload.get("print") or {}
    with _lock:
        for snap in _snapshots.values():
            if snap.get("serial") == serial or (not snap.get("serial")):
                # 单打印机 broker：仅一台设备，直接落快照
                snap["serial"] = serial
                # 拓竹的报告分多条、字段不全：合并策略——新报告缺的字段保留旧值，
                # 避免 remaining_time 等被后续轻量报告覆盖成空。
                if info.get("gcode_state"):
                    snap["state"] = info["gcode_state"]
                    snap["state_text"] = _fmt_state(info["gcode_state"])
                for key, source in (
                    ("percent", "percent"),
                    ("remaining_time", "mc_remaining_time"),  # X1 系列报文字段
                    ("remaining_time", "remaining_time"),
                    ("task_name", "subtask_name"),
                    ("nozzle_temp", "nozzle_temper"),
                    ("bed_temp", "bed_temper"),
                    ("chamber_temp", "chamber_temper"),
                ):
                    val = info.get(source)
                    if val is not None:
                        snap[key] = val
                pf = _clean_print_file(info.get("gcode_file"))
                if pf:
                    snap["print_file"] = pf
                snap["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                break


def _on_disconnect(client, userdata, disconnect_flags, reason_code, properties=None):
    with _lock:
        for snap in _snapshots.values():
            if snap.get("_client_id") == id(client):
                snap["online"] = False
                snap["state_text"] = "离线"


def start_client(printer):
    """为某台打印机启动（或复用）一条 MQTT 连接。"""
    with _lock:
        if printer.id in _clients:
            return
        snap = {
            "_client_id": None,
            "serial": printer.serial,
            "online": False,
            "state_text": "连接中",
        }
        _snapshots[printer.id] = snap

        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"hust3d-{printer.id}-{int(datetime.now().timestamp())}",
            protocol=mqtt.MQTTv311,
        )
        snap["_client_id"] = id(client)
        client.username_pw_set("bblp", printer.access_code)
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)
        client.on_connect = _on_connect
        client.on_message = _on_message
        client.on_disconnect = _on_disconnect

        def loop():
            try:
                # 连接失败会自动重连；连接对象随 daemon 线程存活
                client.connect(printer.ip, 8883, keepalive=30)
                client.loop_forever(retry_first_connection=True)
            except Exception:
                pass

        t = threading.Thread(target=loop, daemon=True, name=f"bambu-{printer.id}")
        t.start()
        _clients[printer.id] = client

        # 首次序列号落库（MQTT 连上后自动发现）
        def _save_serial():
            import time

            for _ in range(40):  # 最多等 20 秒
                time.sleep(0.5)
                with _lock:
                    serial = _snapshots.get(printer.id, {}).get("serial")
                if serial and printer.serial == serial:
                    return
                if serial and not printer.serial:
                    try:
                        with _app.app_context() if _app else _null_ctx():
                            printer.serial = serial
                            db.session.commit()
                    except Exception:
                        db.session.rollback()
                    return

        threading.Thread(target=_save_serial, daemon=True).start()


def stop_client(printer_id):
    with _lock:
        client = _clients.pop(printer_id, None)
        _snapshots.pop(printer_id, None)
    if client:
        try:
            client.disconnect()
            client.loop_stop()
        except Exception:
            pass


class _null_ctx:
    """无 Flask 时的空上下文占位（smoke/脚本场景兜底）。"""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def sync_with_db(app=None):
    """让运行中的连接与数据库里的打印机保持一致（启动/增删时调用）。"""
    global _app
    _app = app
    printers = Printer.query.all()
    with _lock:
        active = {p.id for p in printers}
    for pid in list(_clients.keys()):
        if pid not in active:
            stop_client(pid)
    for p in printers:
        start_client(p)
