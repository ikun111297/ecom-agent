"""飞书渠道：用长连接接收消息，交给 core 里的 Agent 回复"""
import json
import os
from pathlib import Path

import lark_oapi as lark
from dotenv import load_dotenv
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

from core import aftersales, sales

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

APP_ID = os.getenv("FEISHU_APP_ID")
APP_SECRET = os.getenv("FEISHU_APP_SECRET")

_client = lark.Client.builder().app_id(APP_ID).app_secret(APP_SECRET).build()

# 每个用户的会话状态：open_id -> {"mode": 模式, "history": 对话历史}
SESSIONS = {}
SEEN = set()  # 已处理的消息 ID，防止飞书重推导致重复回复

MODES = {"sales": sales, "aftersales": aftersales}


def reply_text(user_id, text):
    """按用户当前模式生成回复"""
    state = SESSIONS.setdefault(user_id, {"mode": "sales", "history": None})

    if text in ("售后", "转售后"):
        state.update(mode="aftersales", history=None)
        return "已切换到【售后服务】，请问有什么可以帮您？"
    if text in ("售前", "转售前"):
        state.update(mode="sales", history=None)
        return "已切换到【售前导购】，请问有什么可以帮您？"

    module = MODES[state["mode"]]
    if state["history"] is None:
        state["history"] = module.new_history()
    return module.ask(text, state["history"])


def send_message(chat_id, text):
    """把回复发回飞书"""
    body = (
        CreateMessageRequestBody.builder()
        .receive_id(chat_id)
        .msg_type("text")
        .content(json.dumps({"text": text}))
        .build()
    )
    req = (
        CreateMessageRequest.builder()
        .receive_id_type("chat_id")
        .request_body(body)
        .build()
    )
    _client.im.v1.message.create(req)


def on_message(data):
    """收到飞书消息时的处理"""
    msg = data.event.message
    if msg.message_id in SEEN:
        return
    SEEN.add(msg.message_id)

    user_id = data.event.sender.sender_id.open_id
    text = json.loads(msg.content).get("text", "").strip()
    text = text.replace("@_user_1", "").strip()  # 群里 @机器人 会带占位符
    if not text:
        return

    print(f"[收到] {text}")
    answer = reply_text(user_id, text)
    print(f"[回复] {answer}")
    send_message(msg.chat_id, answer)


handler = (
    lark.EventDispatcherHandler.builder("", "")
    .register_p2_im_message_receive_v1(on_message)
    .build()
)

ws_client = lark.ws.Client(
    APP_ID, APP_SECRET, event_handler=handler, log_level=lark.LogLevel.WARNING
)


if __name__ == "__main__":
    print("飞书客服已启动，请在飞书里给机器人发消息（Ctrl+C 退出）")
    ws_client.start()