"""Notification routes:测试推送 + 微信 ClawBot 扫码绑定。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.app import auth
from core.notify import ilink
from core.notify import ilink_session
from core.notify import notifier

router = APIRouter(dependencies=[Depends(auth.require_auth)])


class TestBody(BaseModel):
    channel: str


class ChannelIdBody(BaseModel):
    channel_id: str


@router.post("/api/notify/test")
async def notify_test(body: TestBody):
    """测试通道是否可达。返回 {ok, error}。"""
    return await notifier.test_channel(body.channel)


@router.post("/api/notify/wechat_clawbot/qrcode")
async def wechat_qrcode(body: ChannelIdBody):
    """获取登录二维码。通道须已存在于配置中。"""
    ch = ilink_session.find_channel(body.channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="通道不存在,请先保存微信渠道")
    try:
        data = await ilink.get_bot_qrcode()
    except ilink.ILinkError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"获取二维码失败: {e}") from e
    return {
        "channel_id": body.channel_id,
        "qrcode": data.get("qrcode", ""),
        "qrcode_img_content": data.get("qrcode_img_content") or data.get("qrcode", ""),
    }


@router.get("/api/notify/wechat_clawbot/status")
async def wechat_status(
    channel_id: str = Query(...),
    qrcode: str = Query(...),
):
    """轮询扫码状态;confirmed 时写入 bot_token/Bot ID/base_url。"""
    ch = ilink_session.find_channel(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="通道不存在,请先保存微信渠道")
    try:
        data = await ilink.get_qrcode_status(qrcode)
    except ilink.ILinkError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"查询扫码状态失败: {e}") from e

    status = str(data.get("status") or "")
    out = {
        "channel_id": channel_id,
        "status": status,
        "logged_in": False,
    }
    if status == "confirmed":
        token = str(data.get("bot_token") or "").strip()
        if not token:
            raise HTTPException(status_code=502, detail="扫码已确认但未返回 bot_token")
        base_url = str(data.get("baseurl") or data.get("base_url") or "").strip()
        bot_id = str(data.get("ilink_bot_id") or "").strip()
        await ilink_session.apply_login(
            channel_id,
            bot_token=token,
            ilink_bot_id=bot_id,
            base_url=base_url,
        )
        out["logged_in"] = True
        out["message"] = "登录成功,请用微信给该 Bot 发任意消息完成绑定"
    return out


@router.post("/api/notify/wechat_clawbot/logout")
async def wechat_logout(body: ChannelIdBody):
    """退出登录并清理会话与绑定。"""
    ch = ilink_session.find_channel(body.channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="通道不存在")
    await ilink_session.logout(body.channel_id, clear_bind=True)
    return {"ok": True}


@router.get("/api/notify/wechat_clawbot/bind_status")
async def wechat_bind_status(channel_id: str = Query(...)):
    """查询登录/绑定/会话就绪状态。"""
    ch = ilink_session.find_channel(channel_id)
    if not ch:
        raise HTTPException(status_code=404, detail="通道不存在")
    return await ilink_session.bind_status(channel_id)
