# -*- coding: utf-8 -*-
"""读写 .env 配置里的列表型变量（当前用于 ADMIN_STUDENT_IDS）。

为什么要写回文件：登录时角色是按配置里的学号清单重新判定的（见 blueprints/auth.py），
数据库里的 role 只是缓存。所以在页面上添加/移除管理员后，必须把学号同步写回 .env，
否则对方下次登录会被配置覆盖回原来的角色。

写入策略：只改目标那一行，其余内容（注释、其他变量）原样保留；
先写临时文件再 os.replace，避免写到一半把配置损坏。
"""
import os
import re
import tempfile

from flask import current_app

# 没配置 ENV_FILE 时的兜底路径：backend/.env
_DEFAULT_ENV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
)


def env_file_path():
    """当前生效的 .env 路径（可在配置里用 ENV_FILE 覆盖，方便测试）。"""
    return current_app.config.get("ENV_FILE") or _DEFAULT_ENV


def read_text(path):
    """读文本；文件不存在返回 None。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


def set_var(key, value):
    """把 .env 里的单个 KEY=value 改写（保留其它行与注释；原子替换）。

    与 update_list_var 的区别：不做逗号拼接，值里可以带逗号（比如带查询串的 URL）。
    """
    path = env_file_path()
    line = f"{key}={value or ''}"
    pattern = re.compile(rf"^(?P<indent>[ \t]*){re.escape(key)}[ \t]*=.*$", re.MULTILINE)

    text = read_text(path)
    if text is None:
        new_text = f"# 由管理端自动维护：{key}\n{line}\n"
    elif pattern.search(text):
        new_text = pattern.sub(lambda m: f"{m.group('indent')}{line}", text, count=1)
    else:
        base = text
        if base and not base.endswith("\n"):
            base += "\n"
        new_text = f"{base}{line}\n"

    if new_text == text:
        return True

    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".env.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return True


def update_list_var(key, values):
    """把 .env 里的 KEY=a,b,c 改写为 values（列表为空则写成空值）。

    返回值：写入是否成功。文件不存在时会新建一份最小 .env。
    """
    path = env_file_path()
    flat = [str(v).strip() for v in (values or []) if str(v).strip()]
    line = f"{key}={','.join(flat)}"
    pattern = re.compile(rf"^(?P<indent>[ \t]*){re.escape(key)}[ \t]*=.*$", re.MULTILINE)

    text = read_text(path)
    if text is None:
        new_text = f"# 由管理端自动维护：{key}\n{line}\n"
    elif pattern.search(text):
        new_text = pattern.sub(lambda m: f"{m.group('indent')}{line}", text, count=1)
    else:
        base = text
        if base and not base.endswith("\n"):
            base += "\n"
        new_text = f"{base}{line}\n"

    if new_text == text:
        return True

    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".env.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_text)
        os.replace(tmp, path)  # 同分区原子替换
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return True


def set_indexed_vars(prefix, values):
    """把一组值写成 PREFIX、PREFIX_2 ... PREFIX_9（多出来的旧行会删掉）。

    用于短信网关这类"可以有多个监听窗口"的配置：
      SMS_GATEWAY_URL   = 第 1 个
      SMS_GATEWAY_URL_2 = 第 2 个 …
    与 update_list_var 一样：只动这些行，注释和其它变量原样保留，原子替换。
    """
    path = env_file_path()
    flat = []
    for v in (values or []):
        v = str(v).strip()
        if v and v not in flat:
            flat.append(v)

    keys = [prefix] + [f"{prefix}_{i}" for i in range(2, 10)]
    if len(flat) > len(keys):
        flat = flat[:len(keys)]

    text = read_text(path) or ""
    had_newline = text.endswith("\n")
    lines = text.splitlines()

    stale = re.compile(rf"^[ \t]*{re.escape(prefix)}(_\d+)?[ \t]*=.*$")

    # 保持原位置：把整组新行插在第一条出现的地方，其余旧行删掉
    head, tail, inserted, found_at = [], [], False, None
    for i, ln in enumerate(lines):
        if stale.match(ln):
            if found_at is None:
                found_at = i
            continue
        if found_at is None:
            head.append(ln)
        else:
            tail.append(ln)

    new_lines = [f"{keys[idx]}={val}" for idx, val in enumerate(flat)]
    if found_at is None:
        while head and not head[-1].strip():
            head.pop()
        keep = head + new_lines + tail
    else:
        keep = head + new_lines + tail

    new_text = "\n".join(keep) + ("\n" if had_newline or keep else "")
    if new_text == text:
        return True

    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".env.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return True
