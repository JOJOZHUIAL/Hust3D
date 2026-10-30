"""保号定时任务(v2:每设备)+ 每日心跳通知。

保号:每隔 KEEPALIVE_INTERVAL_DAYS 天对每台启用设备发起一次。
动作由 KEEPALIVE_ACTION 决定:ping(蜂窝流量,默认)/sms(发短信)/ussd(查话费类)。
每设备上次执行时间存 kv("keepalive_last_ts:<mac>"),hub 重启不重置。0 天 = 禁用。

心跳:HEARTBEAT_NOTIFY_ENABLED 开启后,每天 HEARTBEAT_NOTIFY_HOUR 点向所有启用
通道发一条存活汇报(直发,不过推送规则)。每天只发一次(kv 记日期)。
"""
import asyncio
import logging
import time

from core.infra import config
from core.infra import db
from core.device import client
from core.device import manager as device_manager
from core.notify import notifier

log = logging.getLogger("keepalive")

CHECK_INTERVAL_S = 3600  # 每小时检查一次是否到期


def _mac(runtime) -> str:
    return client.display_mac(runtime.mac)


async def _keepalive_ping(runtime) -> str:
    """蜂窝流量保号(默认):MIPCALL 建链 → MPING → MIPCALL 释链(省流量)。"""
    def at_ok(r: dict) -> bool:
        return bool(r.get("ok")) and "OK" in (r.get("response") or "")

    r1 = await runtime.at("AT+MIPCALL=1,1", 10000)
    await asyncio.sleep(0.5)
    try:
        r2 = await runtime.at(
            f'AT+MPING="{config.KEEPALIVE_PING_HOST}",10,1', 15000
        )
        await asyncio.sleep(1.0)
    finally:
        await runtime.at("AT+MIPCALL=0,1", 5000)

    ok = at_ok(r1) and at_ok(r2)
    detail = (r2.get("response", "") or "").replace("\r", "").strip()
    if not ok:
        detail = (r1.get("response", "") or "").replace("\r", "").strip() + "\n" + detail
    title = "保号流量已发起" if ok else "保号流量执行异常"
    return notifier.format_system_event(
        f"{title} · {_mac(runtime)}",
        [("目标", config.KEEPALIVE_PING_HOST, True)],
        detail[:200],
    )


async def _keepalive_sms(runtime) -> str:
    """发短信保号:向 KEEPALIVE_TARGET 发一条。"""
    target = config.KEEPALIVE_TARGET
    if not target:
        return notifier.format_system_event(
            f"保号(短信)跳过 · {_mac(runtime)}",
            [("原因", "未配置目标号码", True)],
        )
    try:
        r = await runtime.send(target, "keepalive")
        ok = bool(r.get("ok"))
        err = (r.get("error", "") or "") if not ok else ""
    except client.DeviceBusy:
        return notifier.format_system_event(
            f"保号(短信)设备忙 · {_mac(runtime)}", []
        )
    title = "保号短信已发" if ok else "保号短信失败"
    return notifier.format_system_event(
        f"{title} · {_mac(runtime)}", [("目标", target, True)], err[:200]
    )


async def _run_for_device(runtime) -> str:
    """按 KEEPALIVE_ACTION 分派保号动作。"""
    action = (config.KEEPALIVE_ACTION or "ping").lower()
    if action == "sms":
        return await _keepalive_sms(runtime)
    return await _keepalive_ping(runtime)


async def _maybe_heartbeat_notify():
    """每日心跳通知:到 HEARTBEAT_NOTIFY_HOUR 点发一次,跨天去重。"""
    if not config.HEARTBEAT_NOTIFY_ENABLED:
        return
    now = time.localtime()
    today = time.strftime("%Y-%m-%d", now)
    last = await db.get_kv("heartbeat_notify_last_date", "")
    if now.tm_hour < config.HEARTBEAT_NOTIFY_HOUR or last == today:
        return
    try:
        await notifier.notify_all_channels(
            notifier.format_system_event("每日心跳", [("状态", "Hub 运行中")])
        )
        await db.set_kv("heartbeat_notify_last_date", today)
        log.info("每日心跳通知已发送")
    except Exception as e:
        log.warning("心跳通知异常: %s", e)


async def worker():
    while True:
        try:
            await _maybe_heartbeat_notify()
            # 间隔可在 UI 运行时修改,每轮重读;0 = 禁用
            if config.KEEPALIVE_INTERVAL_DAYS > 0:
                interval_s = config.KEEPALIVE_INTERVAL_DAYS * 86400
                mgr = device_manager.get()
                for mac, runtime in list(mgr.runtimes.items()):
                    if not runtime.base_url:
                        continue
                    key = f"keepalive_last_ts:{mac}"
                    last = float(await db.get_kv(key, "0"))
                    if time.time() - last < interval_s:
                        continue
                    try:
                        result = await _run_for_device(runtime)
                        await db.set_kv(key, str(time.time()))
                        log.info("保号执行完成: %s", mac)
                        await notifier.notify_telegram_direct(result, parse_mode="Markdown")
                    except client.DeviceUnknown:
                        pass  # 设备离线,下个周期再试
                    except Exception as e:
                        log.warning("保号任务异常(%s): %s", mac, e)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("保号任务异常: %s", e)

        await asyncio.sleep(CHECK_INTERVAL_S)
