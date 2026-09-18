# -*- coding: utf-8 -*-
"""对接哈尔滨理工大学教务在线系统（jwzx.hrbust.edu.cn）。

⚠️ 实际系统并非标准 CAS，而是 Spring Security Acegi 登录 + 图形验证码：
  - 登录接口：POST /academic/j_acegi_security_check
  - 字段：    j_username（学号）、j_password（密码）、j_captcha（验证码）
  - 验证码图：GET /academic/getCaptcha.do（与登录共用 JSESSIONID）

因此采用「验证码中转」流程：
  1. 后端先请求验证码图（同时建立 JSESSIONID 会话），把图片 base64 返回前端；
  2. 用户在登录页看到验证码并输入；
  3. 后端用同一会话的 JSESSIONID + 学号 + 密码 + 验证码 提交登录。

⚠️ 安全提示：
  - 学校系统为 HTTP 明文，密码在「我方服务器 → 学校」链路会明文传输，
    这是学校侧现状，我方无法规避（已在 config 中标注）。
  - password 绝不落库、绝不写日志（本文件任何 print/log 都不得包含 password）。
"""
import base64
import os
import re
import time
import uuid

import requests
from bs4 import BeautifulSoup
from flask import current_app


class CasError(Exception):
    """CAS 登录失败（密码错误、验证码错误、网络异常等）。"""


# 验证码会话暂存：captcha_id -> {"cookies": {...}, "exp": 时间戳}
# 注意：进程内存储；gunicorn 多 worker（-w>1）时各 worker 内存不共享，
#       会导致「取验证码」与「提交登录」可能落到不同进程而丢失会话，
#       上线多进程部署时应改用 Redis 等共享存储（本地单进程开发无碍）。
_captcha_store = {}

_UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"),
}


def _base():
    return current_app.config["CAS_BASE_URL"].rstrip("/")


def _new_session():
    s = requests.Session()
    s.headers.update(_UA)
    return s


def fetch_captcha():
    """请求验证码图片，返回 (captcha_id, base64图片, mime)。mock 模式返回 (None, None, None)。"""
    if current_app.config["CAS_MOCK"]:
        return None, None, None

    session = _new_session()
    # 1) 先访问首页建立 JSESSIONID（验证码值绑定在该会话上）
    try:
        session.get(_base() + current_app.config["CAS_HOMEPAGE_URL"], timeout=15)
    except requests.RequestException:
        raise CasError("无法连接教务系统，请稍后再试")

    # 2) 拉取验证码图片
    try:
        resp = session.get(_base() + current_app.config["CAS_CAPTCHA_URL"], timeout=15)
    except requests.RequestException:
        raise CasError("获取验证码失败，请稍后再试")

    captcha_id = uuid.uuid4().hex
    _captcha_store[captcha_id] = {
        "cookies": session.cookies.get_dict(),
        "exp": time.time() + 300,  # 5 分钟内有效
    }
    img_b64 = base64.b64encode(resp.content).decode()
    # 学校返回的是 image/jpeg（非 png），MIME 需透传给前端，否则可能渲染失败
    mime = (resp.headers.get("Content-Type") or "").split(";")[0].strip() or "image/png"
    return captcha_id, img_b64, mime


def _pop_session(captcha_id):
    """取出并删除验证码会话，返回一个已恢复 cookie 的 Session（过期返回 None）。"""
    item = _captcha_store.pop(captcha_id, None)
    if not item or item["exp"] < time.time():
        return None
    s = _new_session()
    s.cookies.update(item["cookies"])
    return s


def cas_login(student_id, password, captcha_id=None, captcha_code=None, need_profile=True):
    """校验学号密码，并按需抓取个人信息。成功返回 (name, college)，失败抛 CasError。

    need_profile=False 时跳过「学籍信息页」抓取（本地已缓存完整姓名/学院时用），
    仅完成密码校验，加快登录并减少对教务系统的访问；此时 name/college 返回空串。
    """
    cfg = current_app.config
    if cfg["CAS_MOCK"]:
        return _mock_login(student_id, password)

    # 恢复验证码会话（与取验证码时同一个 JSESSIONID）
    session = _pop_session(captcha_id)
    if session is None:
        raise CasError("验证码已失效，请刷新后重试")

    payload = {
        "j_username": student_id,
        "j_password": password,  # 仅提交给学校，不落库不记录
        "j_captcha": captcha_code or "",
    }
    try:
        resp = session.post(
            _base() + cfg["CAS_LOGIN_URL"],
            data=payload,
            timeout=15,
            allow_redirects=False,
        )
    except requests.RequestException:
        raise CasError("教务系统无响应，请稍后再试")

    if _login_failed(session, resp):
        raise CasError("学号、密码或验证码错误")

    # 登录成功后按需抓取用户基本信息
    if not need_profile:
        return "", ""

    name, college = _fetch_profile(session, student_id)
    return name, college


def _login_failed(session, resp):
    """判断是否登录失败（已用真实账号验证）。

    Acegi 行为：
      - 成功：302 跳转到 /academic/index_new.jsp（Location 不含 login/error）
      - 失败：302 跳回登录页（Location 含 login 或 ?login_error=1）或 200 错误页
    """
    if resp.status_code in (301, 302, 303):
        loc = (resp.headers.get("Location", "") or "").lower()
        return ("login" in loc) or ("error" in loc)
    # 200：看页面是否出现错误关键字
    text = resp.text or ""
    return ("login_error" in text) or ("验证码" in text and "错误" in text)


def _td_text(td):
    """取 <td> 的纯文本（剔除隐藏 input、必填标记 em 等非文本节点）。"""
    for tag in td.find_all(["input", "em"]):
        tag.decompose()
    return td.get_text(strip=True)


# 学籍信息页字段标签 → 内部字段名。标签文本去掉全/半角冒号后精确匹配。
_PROFILE_LABELS = {
    "姓名": "name",
    "学号": "student_id",
    "院系": "college",
    "学院": "college",
    "所属院系": "college",
    "所在院系": "college",
    "所属学院": "college",
    "院(系)": "college",
    "院（系）": "college",
    "专业": "major",
    "班级": "clazz",
    "年级": "grade",
}


def _parse_profile_table(soup):
    """解析学籍信息表格，返回 {字段: 值}。

    兼容多种结构：
      - <th>标签</th><td>值</td>
      - <td>标签</td><td>值</td>
      - 一行多对：<th>..</th><td>..</td><th>..</th><td>..</td>
    做法：逐行收集所有单元格纯文本，按「标签在前、值在后」逐对匹配。
    """
    out = {}
    for tr in soup.find_all("tr"):
        texts = []
        for cell in tr.find_all(["th", "td"]):
            t = _td_text(cell)
            if t:
                texts.append(t)
        i = 0
        while i < len(texts) - 1:
            label = texts[i].replace("：", "").replace(":", "").strip()
            value = texts[i + 1].strip()
            if label in _PROFILE_LABELS:
                out.setdefault(_PROFILE_LABELS[label], value)
                i += 2
            else:
                i += 1
    return out


def _debug_dump_profile(soup, url, status):
    """（仅调试）把学籍页结构摘要写入文件，用于定位「学院」字段。

    只写字段标签与含「院/系/专业/班/级」的短片段（字段名），不写姓名/学号等长值，
    避免把个人敏感信息落盘。
    """
    try:
        title = soup.find("title")
        lines = [
            f"URL={url}",
            f"STATUS={status}",
            f"TITLE={title.get_text(strip=True) if title else ''}",
            f"TH_TAGS={' | '.join(th.get_text(strip=True) for th in soup.find_all('th'))}",
        ]
        related = []
        for s in soup.stripped_strings:
            if any(k in s for k in ("院", "系", "专业", "班", "级")) and len(s) <= 20:
                related.append(s)
        lines.append(f"RELATED={' | '.join(related)}")
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_cas_debug.txt"
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception:
        pass


def _fetch_profile(session, student_id):
    """登录成功后抓取姓名/学院。

    优先抓「学籍信息」页（CAS_INFO_URL），解析 姓名 与 院系；若未配置或
    抓取失败，回退抓顶部横幅 showHeader.do 里的「您好！XXX(学号)」提取姓名。
    都失败时返回空值。
    """
    cfg = current_app.config
    name = college = ""

    # 1) 学籍信息页：姓名 + 院系
    info_url = cfg["CAS_INFO_URL"]
    if info_url:
        resp = None
        try:
            resp = session.get(_base() + info_url, timeout=15)
        except requests.RequestException:
            resp = None
        if resp is not None:
            # 学校页面多为 GBK/UTF-8，HTTP 头未必带 charset，按实测编码兜底
            if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding
            soup = BeautifulSoup(resp.text, "html.parser")
            info = _parse_profile_table(soup)
            name = info.get("name", "")
            college = info.get("college", "")
            if cfg.get("CAS_DEBUG"):
                _debug_dump_profile(soup, _base() + info_url, resp.status_code)

    # 2) 回退：顶部横幅提取姓名
    if not name:
        try:
            resp = session.get(_base() + "/academic/showHeader.do", timeout=15)
            if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding
            text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)
            m = re.search(r"您好[！!]?\s*(.+?)\s*[\(（]", text)
            if m:
                name = m.group(1).strip()
        except requests.RequestException:
            pass

    return name, college


def _mock_login(student_id, password):
    """本地开发用：不连学校系统，仅做格式校验。"""
    if not student_id or not password:
        raise CasError("学号和密码不能为空")
    if len(student_id) < 6:
        raise CasError("学号格式不正确")
    return (f"测试用户{student_id[-3:]}", "创新创业学院")
