"""选择性推送规则评估:按规则决定一条消息发往哪些通道。

规则存 ``config.PUSH_RULES``(list[dict]),与 ``notify_channels`` 同模式走
``kv("cfg").notify_rules``。评估语义:

- ``PUSH_RULES_ENABLED`` 关 / 无启用规则 / 未命中任何规则 → 全发(所有 enabled 通道)
- 按 ``priority`` 升序评估启用规则,首条命中即停:
    - ``drop=True``            → 不发任何通道(入库但不打扰)
    - ``channel_ids`` 为空      → 全发(命中但不限制,用于"仅排除"型规则)
    - ``channel_ids`` 非空      → 只发 ``enabled ∩ channel_ids``

纯函数,无副作用,便于单测。调用方(notifier)传入 ``_enabled_channels()`` 的结果
作为 ``all_channels``,本模块只在规则维度做过滤,不重复 enabled 判定。
"""
import re

from core.infra import config


def _match(rule: dict, ctx: dict) -> bool:
    typ = rule.get("match_type")
    val = rule.get("match_value", "")
    if typ == "all":
        return True
    if typ == "code_present":
        return bool(ctx.get("code"))
    if typ == "keyword":
        return bool(val) and val in (ctx.get("text") or "")
    if typ == "sender":
        if not val:
            return False
        try:
            return re.search(val, ctx.get("sender") or "") is not None
        except re.error:
            # 非法正则不阻断投递,视为不命中
            return False
    if typ == "sim_id":
        return bool(val) and val == (ctx.get("sim_id") or "")
    return False


def select_channels_for_message(
    ctx: dict,
    rules: list[dict] | None = None,
    all_channels: list[dict] | None = None,
) -> list[dict]:
    """返回这条消息应投递的通道子集。

    - ``all_channels`` 默认 ``config.NOTIFY_CHANNELS``;调用方应传 notifier 的
      ``_enabled_channels()``(已过滤 enabled 且 target 有效)。
    - ``rules`` 默认 ``config.PUSH_RULES``。
    """
    channels = all_channels if all_channels is not None else config.NOTIFY_CHANNELS
    if rules is None:
        rules = config.PUSH_RULES
    # 开关关闭 → 全发(与 docstring/UI 语义一致;此前开关从未被读取,规则恒生效)
    if not config.PUSH_RULES_ENABLED:
        return list(channels)
    # 无启用规则 → 默认全发(向后兼容:未配置/全停用规则时行为=全发)
    # 按 priority 升序评估启用规则(stable sort 保证同 priority 按配置顺序)
    active = sorted(
        (r for r in rules if r.get("enabled")),
        key=lambda r: r.get("priority", 100),
    )
    sim_id = ctx.get("sim_id")
    for r in active:
        # 可选 sim_id 限定:规则绑了卡且与当前消息卡不符则跳过
        if r.get("sim_id") and r["sim_id"] != sim_id:
            continue
        if not _match(r, ctx):
            continue
        # 命中首条
        if r.get("drop"):
            return []
        ids = r.get("channel_ids") or []
        if not ids:
            return list(channels)
        allow = {str(x) for x in ids}
        return [c for c in channels if c.get("id") in allow]
    # 未命中任何规则 → 全发
    return list(channels)
