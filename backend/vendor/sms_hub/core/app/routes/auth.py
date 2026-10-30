"""Login routes."""
import secrets
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.app import auth
from core.infra import config

router = APIRouter()

# 登录限流:按来源 IP 连续失败锁定(可信局域网前提下的纵深防御)。
_MAX_FAILS = 5        # 连续失败 N 次触发锁定
_LOCK_SECONDS = 60    # 锁定秒数
_FAIL_STATE_MAX = 1000
_fail_state: dict[str, tuple[int, float]] = {}


def _prune_fail_state(now: float):
    if len(_fail_state) <= _FAIL_STATE_MAX:
        return
    for peer in [p for p, (_, ts) in _fail_state.items() if now - ts > _LOCK_SECONDS]:
        _fail_state.pop(peer, None)


class LoginBody(BaseModel):
    user: str
    password: str


@router.post("/api/login")
async def login(body: LoginBody, request: Request):
    peer = request.client.host if request.client else "?"
    now = time.time()
    _prune_fail_state(now)
    fails, first_fail = _fail_state.get(peer, (0, 0.0))
    if fails >= _MAX_FAILS and now - first_fail < _LOCK_SECONDS:
        raise HTTPException(status_code=429, detail="尝试过于频繁,请稍后再试")
    if body.user == config.WEBUI_USER and secrets.compare_digest(
        body.password, config.WEBUI_PASS
    ):
        _fail_state.pop(peer, None)  # 登录成功清零
        return {"token": auth.make_token(body.user)}
    if now - first_fail > _LOCK_SECONDS:
        fails, first_fail = 0, now  # 锁定窗口已过,重新计数
    _fail_state[peer] = (fails + 1, first_fail)
    raise HTTPException(status_code=401, detail="账号或密码错误")
