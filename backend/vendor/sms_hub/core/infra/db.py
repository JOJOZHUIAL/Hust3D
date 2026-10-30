"""SQLite 存储:v2 多设备 schema 与常用查询。

v2 数据模型(见 docs/guide.md「四、数据模型」):共享表 + `sim_id` 业务分区
+ `device_mac` 物理审计。物理瘦终端以 `device_mac` 标识链路,SIM 卡以
`sim_id`(IMSI 派生)标识短信业务归属。墓碑按 `(device_mac, gw_epoch,
device_msg_id)` 复合主键隔离,防不同设备同编号短信互相影响。

全新安装(SCHEMA_VERSION=4),不写旧版迁移。开启 PRAGMA foreign_keys=ON。

事务边界约定(与 v1 一致):`insert_message` **不 commit**,由调用方把
"插入消息 + 关联通知入队 + 推进游标"作为同一事务提交。所有写助手带
`commit=True` 默认值,poller 内部传 `commit=False` 串进单事务。

连接一致性(v2 修复):全进程共享单连接 + Python sqlite3 隐式事务下,
poller 的多语句事务会被其他任务(webhook/其他设备 poller/sender/notifier)
的语句 join——其他任务的 commit 会提前提交 poller 中间状态(消息入库而
通知未入队),poller 的 rollback 会吞掉其他任务未提交写入。现在连接以
`isolation_level=None`(autocommit)打开 + 语句级互斥代理:`db.transaction()`
跨语句持锁执行显式 BEGIN IMMEDIATE 事务,窗口内其他任务的语句排队等待
不 join;窗口外单语句立即提交,rollback 不再波及无关写入。
"""
import asyncio
import contextlib
import time
from datetime import datetime, timedelta

import aiosqlite

from core.infra import config

SCHEMA_VERSION = 4

SCHEMA = """
-- 物理瘦终端:MAC 为主键,业务身份挂在 current_sim_id。
CREATE TABLE IF NOT EXISTS devices (
    mac                 TEXT PRIMARY KEY,
    name                TEXT NOT NULL DEFAULT '',
    enabled             INTEGER NOT NULL DEFAULT 1,
    base_url            TEXT NOT NULL DEFAULT '',
    current_sim_id      TEXT NOT NULL DEFAULT '',
    cursor              INTEGER NOT NULL DEFAULT 0,
    gw_epoch            INTEGER NOT NULL DEFAULT 0,
    heartbeat_interval_s INTEGER NOT NULL DEFAULT 60,
    last_hook_ts        REAL NOT NULL DEFAULT 0,
    last_poll_ok_ts     REAL NOT NULL DEFAULT 0,
    last_status_ts      REAL NOT NULL DEFAULT 0,
    last_status_json    TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- SIM 卡:identity_source ∈ {imsi, temporary};imsi_hash 全量唯一(空=临时卡)。
CREATE TABLE IF NOT EXISTS sims (
    sim_id              TEXT PRIMARY KEY,
    name                TEXT NOT NULL DEFAULT '',
    enabled             INTEGER NOT NULL DEFAULT 1,
    current_device_mac  TEXT NOT NULL DEFAULT '',
    identity_source     TEXT NOT NULL DEFAULT 'imsi',
    imsi_hash           TEXT NOT NULL DEFAULT '',
    imsi_tail           TEXT NOT NULL DEFAULT '',
    iccid_tail          TEXT NOT NULL DEFAULT '',
    msisdn              TEXT NOT NULL DEFAULT '',
    operator            TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sims_imsi_hash
    ON sims(imsi_hash) WHERE imsi_hash <> '';

-- 收件箱:sim_id 业务归属 + device_mac 物理审计;跨设备同编号靠复合 UNIQUE 去重。
-- scts 保留用于断电恢复时间兜底(docs/guide.md 数据模型字段表未列,但可靠性需要)。
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_id      TEXT NOT NULL REFERENCES sims(sim_id),
    device_mac  TEXT NOT NULL,
    device_msg_id INTEGER NOT NULL,
    gw_epoch    INTEGER NOT NULL DEFAULT 0,
    sender      TEXT NOT NULL,
    text        TEXT NOT NULL,
    scts        TEXT NOT NULL DEFAULT '',
    received_at TEXT NOT NULL,
    code        TEXT,
    complete    INTEGER NOT NULL DEFAULT 1,
    truncated   INTEGER NOT NULL DEFAULT 0,
    blocked     INTEGER NOT NULL DEFAULT 0,
    content_type TEXT NOT NULL DEFAULT 'sms',
    mms_url     TEXT NOT NULL DEFAULT '',
    mms_size    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE(device_mac, gw_epoch, device_msg_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_received ON messages(received_at);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender);
CREATE INDEX IF NOT EXISTS idx_messages_sim ON messages(sim_id, received_at);

-- 删除墓碑:按设备维度复合主键;sim_id 非 FK(卡可删,墓碑留到 TOMBSTONE_KEEP_DAYS)。
CREATE TABLE IF NOT EXISTS deleted_messages (
    sim_id        TEXT NOT NULL DEFAULT '',
    device_mac    TEXT NOT NULL,
    gw_epoch      INTEGER NOT NULL,
    device_msg_id INTEGER NOT NULL,
    deleted_at    REAL NOT NULL DEFAULT (strftime('%s','now')),
    PRIMARY KEY(device_mac, gw_epoch, device_msg_id)
);

-- 出站队列:sim_id 业务归属 + 实际承载 device_mac。
CREATE TABLE IF NOT EXISTS outbound (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_id      TEXT NOT NULL REFERENCES sims(sim_id),
    device_mac  TEXT NOT NULL DEFAULT '',
    to_phone    TEXT NOT NULL,
    text        TEXT NOT NULL,
    device_msg_id INTEGER,
    status      TEXT NOT NULL DEFAULT 'pending',
    parts       INTEGER NOT NULL DEFAULT 0,
    attempts    INTEGER NOT NULL DEFAULT 0,
    next_attempt_ts REAL NOT NULL DEFAULT 0,
    source      TEXT NOT NULL DEFAULT 'webui',
    last_error  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_outbound_status ON outbound(status, next_attempt_ts);
CREATE INDEX IF NOT EXISTS idx_outbound_sim ON outbound(sim_id);

-- 通知任务:按消息引用,删消息级联删通知。重试列保留(notifier 退避需要)。
CREATE TABLE IF NOT EXISTS notify_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_id          INTEGER REFERENCES messages(id) ON DELETE CASCADE,
    channel         TEXT NOT NULL,
    target          TEXT NOT NULL DEFAULT '',
    text            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_ts REAL NOT NULL DEFAULT 0,
    last_error      TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_notify_status ON notify_jobs(status, next_attempt_ts);
CREATE INDEX IF NOT EXISTS idx_notify_msg ON notify_jobs(msg_id);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
    phone      TEXT PRIMARY KEY,
    alias      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""

_db: "_LockedConn | None" = None


class _LockedResult:
    """execute/executescript 的返回值:async with / await 双形态,
    与 aiosqlite 原生 Result 一致(调用方零改动)。语句真正执行发生在
    __aenter__ / await 时刻,代理把"执行"放到互斥锁内。"""

    __slots__ = ("_coro", "_obj")

    def __init__(self, coro):
        self._coro = coro
        self._obj = None

    def send(self, value):
        return self._coro.send(value)

    def throw(self, typ, val=None, tb=None):
        if val is None:
            return self._coro.throw(typ)
        if tb is None:
            return self._coro.throw(typ, val)
        return self._coro.throw(typ, val, tb)

    def close(self):
        return self._coro.close()

    def __await__(self):
        return self._coro.__await__()

    async def __aenter__(self):
        obj = await self._coro
        self._obj = obj
        return obj

    async def __aexit__(self, exc_type, exc, tb):
        obj = self._obj
        if obj is not None:
            await obj.close()


class _LockedConn:
    """共享连接的语句级互斥代理(见模块 docstring 的连接一致性说明)。

    - 窗口外:每条语句的执行在互斥下进行;autocommit 模式下单语句立即
      提交,rollback/commit 不再波及无关写入。
    - 窗口内(`transaction()`):跨语句持锁,其他任务(webhook/sender/
      notifier/其他设备 poller)的任何语句排队等待,不会 join 本事务。
    - execute/executescript 返回 _LockedResult(双形态),调用方零改动。
    """

    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn
        self._lock = asyncio.Lock()
        self._in_tx = False
        self._tx_owner: asyncio.Task | None = None

    def _in_tx_now(self) -> bool:
        # 仅事务发起者(task)的语句直通;其他任务在窗口内必须等锁,
        # 否则会 join 进显式事务并被其 COMMIT/ROLLBACK 波及
        return self._in_tx and self._tx_owner is asyncio.current_task()

    def execute(self, sql: str, params=()):
        return _LockedResult(self._run_execute(sql, params))

    def executescript(self, sql: str):
        return _LockedResult(self._run_executescript(sql))

    async def _run_execute(self, sql: str, params=()):
        if self._in_tx_now():
            return await self._exec_cursor(self._conn._conn.execute, sql, params)
        async with self._lock:
            return await self._exec_cursor(self._conn._conn.execute, sql, params)

    async def _run_executescript(self, sql: str):
        if self._in_tx_now():
            return await self._exec_script(self._conn._conn.executescript, sql)
        async with self._lock:
            return await self._exec_script(self._conn._conn.executescript, sql)

    async def _exec_cursor(self, fn, sql: str, params=()):
        # 同 aiosqlite 原生 execute:裸 sqlite3 cursor 必须包成 aiosqlite.Cursor
        # (fetchall/close 等走后台线程队列),否则主线程直触 sqlite3 对象报线程错误
        cursor = await self._conn._execute(fn, sql, params)
        return aiosqlite.Cursor(self._conn, cursor)

    async def _exec_script(self, fn, sql: str):
        # executescript 只接受一个参数,与 _exec_cursor 分开处理
        cursor = await self._conn._execute(fn, sql)
        return aiosqlite.Cursor(self._conn, cursor)

    async def commit(self):
        if self._in_tx_now():
            return await self._conn.commit()
        async with self._lock:
            return await self._conn.commit()

    async def rollback(self):
        if self._in_tx_now():
            return await self._conn.rollback()
        async with self._lock:
            return await self._conn.rollback()

    async def close(self):
        async with self._lock:
            return await self._conn.close()


@contextlib.asynccontextmanager
async def transaction():
    """显式 BEGIN IMMEDIATE 事务:poller 批次等"多语句原子提交"的入口。

    跨语句持有连接互斥锁:窗口内其他任务的任何语句排队等待,不会 join
    本事务(其 commit 提前提交中间状态 / poller rollback 吞写入);异常
    自动 ROLLBACK,正常结束统一 COMMIT。窗口内语句不走锁(直通),无死锁。
    """
    conn = db()
    async with conn._lock:
        conn._in_tx = True
        conn._tx_owner = asyncio.current_task()
        try:
            await conn.execute("BEGIN IMMEDIATE")
            yield conn
        except BaseException:
            await conn.rollback()
            raise
        else:
            await conn.commit()
        finally:
            conn._in_tx = False
            conn._tx_owner = None


async def open_db() -> _LockedConn:
    global _db
    raw = await aiosqlite.connect(config.DB_PATH, isolation_level=None)  # autocommit
    raw.row_factory = aiosqlite.Row
    # WAL:写入更稳、崩溃不损坏主库。备份请用 sqlite3 .backup 而非直接 cp
    await raw.execute("PRAGMA journal_mode=WAL")
    await raw.execute("PRAGMA synchronous=NORMAL")
    await raw.execute("PRAGMA busy_timeout=5000")
    await raw.execute("PRAGMA foreign_keys=ON")
    # 读调优:放大 page cache、临时表入内存、mmap。
    await raw.execute("PRAGMA temp_store=MEMORY")    # 临时表与排序走内存
    await raw.execute("PRAGMA cache_size=-65536")    # 64MB page cache(负值=KB)
    await raw.execute("PRAGMA mmap_size=268435456")  # 256MB mmap 读上限(实际按库大小用)
    _db = _LockedConn(raw)
    await _db.executescript(SCHEMA)
    await _migrate_messages_mms()
    await _sanitize_device_snapshots()
    await _record_schema_version()
    await _db.commit()
    return _db


async def _sanitize_device_snapshots():
    """清洗 devices.last_status_json 中可能遗留的完整 IMSI/ICCID(§1.5)。
    幂等:已脱敏行不解码 JSON,无敏感字段不更新。"""
    import json as _json
    async with db().execute(
        "SELECT mac, last_status_json FROM devices WHERE last_status_json <> ''"
    ) as cur:
        rows = list(await cur.fetchall())
    cleaned = 0
    for r in rows:
        # 快速跳过:JSON 中不含完整身份字面量时可免解码
        raw = r["last_status_json"]
        if '"imsi"' not in raw and '"iccid"' not in raw:
            continue
        try:
            obj = _json.loads(raw)
        except _json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        modem = obj.get("modem")
        if not isinstance(modem, dict):
            continue
        changed = False
        # 保留用 imsi/iccid 提取的尾号(若快照中 tail 尚未存在)
        imsi = str(modem.pop("imsi", "") or "")
        if imsi:
            changed = True
            if not modem.get("imsi_tail"):
                modem["imsi_tail"] = imsi[-4:]
        iccid = str(modem.pop("iccid", "") or "")
        if iccid:
            changed = True
            if not modem.get("iccid_tail"):
                modem["iccid_tail"] = iccid[-4:]
        if changed:
            await db().execute(
                "UPDATE devices SET last_status_json=? WHERE mac=?",
                (_json.dumps(obj, ensure_ascii=False), r["mac"]),
            )
            cleaned += 1
    if cleaned:
        import logging
        logging.getLogger("db").info(
            "已清洗 %d 个含完整身份的设备快照", cleaned
        )


async def _migrate_messages_mms():
    """既有库补 messages 的 MMS 列(CREATE IF NOT EXISTS 只对新库生效)。幂等。"""
    async with db().execute("PRAGMA table_info(messages)") as cur:
        cols = {r[1] for r in await cur.fetchall()}
    if "content_type" not in cols:
        await db().execute(
            "ALTER TABLE messages ADD COLUMN content_type TEXT NOT NULL DEFAULT 'sms'"
        )
    if "mms_url" not in cols:
        await db().execute(
            "ALTER TABLE messages ADD COLUMN mms_url TEXT NOT NULL DEFAULT ''"
        )
    if "mms_size" not in cols:
        await db().execute(
            "ALTER TABLE messages ADD COLUMN mms_size INTEGER NOT NULL DEFAULT 0"
        )


def db() -> _LockedConn:
    assert _db is not None, "db not opened"
    return _db


async def close_db():
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def _maybe_commit(commit: bool):
    if commit:
        await db().commit()


# ── kv ──

async def get_kv(key: str, default: str = "") -> str:
    async with db().execute("SELECT value FROM kv WHERE key=?", (key,)) as cur:
        row = await cur.fetchone()
    return row["value"] if row else default


async def set_kv(key: str, value: str):
    await db().execute(
        "INSERT INTO kv(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    await db().commit()


# ── contacts ──

async def fetch_sender_alias(phone: str) -> str:
    """查发件人通讯录备注名,用于推送模板的 {sender_name} 占位符。无则空串。"""
    async with db().execute(
        "SELECT alias FROM contacts WHERE phone=?", (phone,)
    ) as cur:
        row = await cur.fetchone()
    return row["alias"] if row else ""


# ── devices ──

async def get_device(mac: str) -> aiosqlite.Row | None:
    async with db().execute("SELECT * FROM devices WHERE mac=?", (mac,)) as cur:
        return await cur.fetchone()


async def list_enabled_devices() -> list[aiosqlite.Row]:
    async with db().execute(
        "SELECT * FROM devices WHERE enabled=1 ORDER BY created_at"
    ) as cur:
        return list(await cur.fetchall())


async def list_all_devices() -> list[aiosqlite.Row]:
    async with db().execute("SELECT * FROM devices ORDER BY created_at") as cur:
        return list(await cur.fetchall())


async def upsert_device(
    mac: str,
    *,
    base_url: str | None = None,
    heartbeat_interval_s: int | None = None,
    enabled: int | None = None,
    commit: bool = True,
) -> None:
    """注册或更新物理设备。仅更新身份/链路字段,name 由用户在 UI 改(独立接口)。
    用 excluded.<col> UPSERT:提供的字段在新建与冲突更新时都生效。"""
    fields = {
        "base_url": base_url,
        "heartbeat_interval_s": int(heartbeat_interval_s) if heartbeat_interval_s is not None else None,
        "enabled": int(bool(enabled)) if enabled is not None else None,
    }
    cols, vals, sets = ["mac"], [mac], []
    for col, val in fields.items():
        if val is not None:
            cols.append(col)
            vals.append(val)
            sets.append(f"{col}=excluded.{col}")
    sets.append("updated_at=datetime('now','localtime')")
    sql = (f"INSERT INTO devices({','.join(cols)}) VALUES ({','.join('?' for _ in vals)}) "
           f"ON CONFLICT(mac) DO UPDATE SET {','.join(sets)}")
    await db().execute(sql, vals)
    await _maybe_commit(commit)


async def set_device_base_url(mac: str, base_url: str, *, commit: bool = True):
    await db().execute(
        "UPDATE devices SET base_url=?, updated_at=datetime('now','localtime') WHERE mac=?",
        (base_url, mac),
    )
    await _maybe_commit(commit)


async def set_device_current_sim(mac: str, sim_id: str, *, commit: bool = True):
    await db().execute(
        "UPDATE devices SET current_sim_id=?, updated_at=datetime('now','localtime') WHERE mac=?",
        (sim_id, mac),
    )
    await _maybe_commit(commit)


async def set_device_cursor_epoch(
    mac: str, *, cursor: int, gw_epoch: int, commit: bool = True
):
    await db().execute(
        "UPDATE devices SET cursor=?, gw_epoch=?,"
        " updated_at=datetime('now','localtime') WHERE mac=?",
        (int(cursor), int(gw_epoch), mac),
    )
    await _maybe_commit(commit)


async def update_device_timestamps(
    mac: str,
    *,
    last_hook_ts: float | None = None,
    last_poll_ok_ts: float | None = None,
    last_status_ts: float | None = None,
    commit: bool = True,
):
    sets, params = [], []
    if last_hook_ts is not None:
        sets.append("last_hook_ts=?")
        params.append(float(last_hook_ts))
    if last_poll_ok_ts is not None:
        sets.append("last_poll_ok_ts=?")
        params.append(float(last_poll_ok_ts))
    if last_status_ts is not None:
        sets.append("last_status_ts=?")
        params.append(float(last_status_ts))
    if not sets:
        return
    sets.append("updated_at=datetime('now','localtime')")
    params.append(mac)
    await db().execute(
        f"UPDATE devices SET {', '.join(sets)} WHERE mac=?", params
    )
    await _maybe_commit(commit)


async def update_device_status_snapshot(
    mac: str, status_json: str, last_status_ts: float, *, commit: bool = True
):
    await db().execute(
        "UPDATE devices SET last_status_json=?, last_status_ts=?,"
        " updated_at=datetime('now','localtime') WHERE mac=?",
        (status_json, float(last_status_ts), mac),
    )
    await _maybe_commit(commit)


async def set_device_enabled(mac: str, enabled: bool, *, commit: bool = True):
    await db().execute(
        "UPDATE devices SET enabled=?, updated_at=datetime('now','localtime') WHERE mac=?",
        (1 if enabled else 0, mac),
    )
    await _maybe_commit(commit)


async def set_device_name(mac: str, name: str, *, commit: bool = True):
    await db().execute(
        "UPDATE devices SET name=?, updated_at=datetime('now','localtime') WHERE mac=?",
        (name, mac),
    )
    await _maybe_commit(commit)


# ── sims ──

async def get_sim(sim_id: str) -> aiosqlite.Row | None:
    async with db().execute("SELECT * FROM sims WHERE sim_id=?", (sim_id,)) as cur:
        return await cur.fetchone()


async def get_sim_by_imsi_hash(imsi_hash: str) -> aiosqlite.Row | None:
    if not imsi_hash:
        return None
    async with db().execute(
        "SELECT * FROM sims WHERE imsi_hash=?", (imsi_hash,)
    ) as cur:
        return await cur.fetchone()


async def list_sims() -> list[aiosqlite.Row]:
    async with db().execute("SELECT * FROM sims ORDER BY created_at") as cur:
        return list(await cur.fetchall())


async def upsert_sim(
    sim_id: str,
    *,
    name: str | None = None,
    enabled: int | None = None,
    identity_source: str | None = None,
    current_device_mac: str | None = None,
    imsi_hash: str | None = None,
    imsi_tail: str | None = None,
    iccid_tail: str | None = None,
    msisdn: str | None = None,
    operator: str | None = None,
    commit: bool = True,
) -> None:
    """注册或更新 SIM 卡。设备上报只刷新身份字段(imsi/iccid/msisdn/operator/
    identity_source/current_device_mac),**不动 name/enabled**(用户控制)。
    name/enabled 仅在显式传入时(用户 PATCH)才写。用 excluded.<col> UPSERT,
    提供的字段在新建与冲突更新时都生效。"""
    fields = {
        "name": name,
        "enabled": int(bool(enabled)) if enabled is not None else None,
        "identity_source": identity_source,
        "current_device_mac": current_device_mac,
        "imsi_hash": imsi_hash,
        "imsi_tail": imsi_tail,
        "iccid_tail": iccid_tail,
        "msisdn": msisdn,
        "operator": operator,
    }
    cols, vals, sets = ["sim_id"], [sim_id], []
    for col, val in fields.items():
        if val is not None:
            cols.append(col)
            vals.append(val)
            sets.append(f"{col}=excluded.{col}")
    sets.append("updated_at=datetime('now','localtime')")
    sql = (f"INSERT INTO sims({','.join(cols)}) VALUES ({','.join('?' for _ in vals)}) "
           f"ON CONFLICT(sim_id) DO UPDATE SET {','.join(sets)}")
    await db().execute(sql, vals)
    await _maybe_commit(commit)


async def reassign_sim_business(old_sim_id: str, new_sim_id: str, *, commit: bool = True):
    """把旧 sim_id 的全部业务(消息/发件/墓碑)改写到新 sim_id,再删旧卡行。
    调用方须先确保新 sim_id 已存在(FK)。用于临时卡→稳定卡合并。"""
    if old_sim_id == new_sim_id or not old_sim_id:
        return
    await db().execute(
        "UPDATE messages SET sim_id=? WHERE sim_id=?", (new_sim_id, old_sim_id)
    )
    await db().execute(
        "UPDATE outbound SET sim_id=? WHERE sim_id=?", (new_sim_id, old_sim_id)
    )
    await db().execute(
        "UPDATE deleted_messages SET sim_id=? WHERE sim_id=?", (new_sim_id, old_sim_id)
    )
    await db().execute("DELETE FROM sims WHERE sim_id=?", (old_sim_id,))
    await _maybe_commit(commit)


# ── messages ──

async def insert_message(m: dict) -> int | None:
    """插入消息,命中墓碑或复合 UNIQUE 已存在时返回 None,否则返回新行 id。
    不 commit:由调用方把"插入消息 + 通知入队 + 游标推进"作为同一事务提交。"""
    triple = (m["device_mac"], int(m["gw_epoch"]), int(m["device_msg_id"]))
    async with db().execute(
        "SELECT 1 FROM deleted_messages "
        "WHERE device_mac=? AND gw_epoch=? AND device_msg_id=?",
        triple,
    ) as cur:
        if await cur.fetchone():
            return None
    cur = await db().execute(
        "INSERT OR IGNORE INTO messages"
        "(sim_id, device_mac, device_msg_id, gw_epoch, sender, text, scts,"
        " received_at, code, complete, truncated, blocked,"
        " content_type, mms_url, mms_size)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            m["sim_id"], m["device_mac"], int(m["device_msg_id"]), int(m["gw_epoch"]),
            m["sender"], m["text"], m.get("scts", ""),
            m["received_at"], m.get("code"),
            1 if m.get("complete", True) else 0,
            1 if m.get("truncated", False) else 0,
            1 if m.get("blocked", False) else 0,
            m.get("content_type", "sms"), m.get("mms_url", ""), int(m.get("mms_size", 0)),
        ),
    )
    return cur.lastrowid if cur.rowcount > 0 else None


async def tombstone_messages(
    triples: list[tuple[str, int, int, str]], *, commit: bool = True
):
    """把已删除的 (device_mac, gw_epoch, device_msg_id, sim_id) 写墓碑,防回流。"""
    if not triples:
        return
    for device_mac, gw_epoch, device_msg_id, sim_id in triples:
        await db().execute(
            "INSERT OR IGNORE INTO deleted_messages"
            "(sim_id, device_mac, gw_epoch, device_msg_id) VALUES(?,?,?,?)",
            (sim_id, device_mac, int(gw_epoch), int(device_msg_id)),
        )
    await _maybe_commit(commit)


async def fetch_synced_device_ids(
    device_mac: str, device_msg_ids: list[int], gw_epoch: int
) -> list[int]:
    """给定一组 device_msg_id,返回其中已同步到 Hub 库的(按 mac + 当前 epoch 匹配)。
    用于手动排空设备缓冲——只删已同步的,未同步的保留以便继续拉取。
    必须限定 gw_epoch:换机/重置后设备编号重新从 0 计,跨 epoch 匹配
    (旧代次已同步的同 id 消息)会误删尚未同步的新消息。"""
    if not device_msg_ids:
        return []
    ph = ",".join("?" for _ in device_msg_ids)
    async with db().execute(
        f"SELECT DISTINCT device_msg_id FROM messages WHERE device_mac=?"
        f" AND gw_epoch=? AND device_msg_id IN ({ph})",
        [device_mac, int(gw_epoch), *device_msg_ids],
    ) as cur:
        return [r["device_msg_id"] for r in await cur.fetchall()]


async def cleanup_tombstones(keep_days: int = 30):
    """清理超过 N 天的墓碑记录。"""
    cutoff = time.time() - keep_days * 86400
    await db().execute("DELETE FROM deleted_messages WHERE deleted_at < ?", (cutoff,))
    await db().commit()


async def cleanup_old_messages(keep_days: int = 0) -> int:
    """Delete messages older than keep_days and tombstone their (mac,epoch,id) triples."""
    if keep_days <= 0:
        return 0
    cutoff = (datetime.now() - timedelta(days=keep_days)).replace(
        microsecond=0
    ).isoformat(sep=" ")
    async with db().execute(
        "SELECT id, sim_id, device_mac, gw_epoch, device_msg_id"
        " FROM messages WHERE received_at < ?",
        (cutoff,),
    ) as cur:
        rows = await cur.fetchall()
    if not rows:
        return 0
    await tombstone_messages(
        [(r["device_mac"], r["gw_epoch"], r["device_msg_id"], r["sim_id"]) for r in rows],
        commit=False,
    )
    ids = [r["id"] for r in rows]
    placeholders = ",".join("?" for _ in ids)
    # messages 删除级联清 notify_jobs(ON DELETE CASCADE)
    await db().execute(f"DELETE FROM messages WHERE id IN ({placeholders})", ids)
    await db().commit()
    return len(ids)


async def _record_schema_version():
    """Record the current fresh-install schema baseline."""
    assert _db is not None
    await _db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    await _db.execute(
        "INSERT INTO kv(key,value) VALUES('schema_version',?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(SCHEMA_VERSION),),
    )
