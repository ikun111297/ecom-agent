"""飞书渠道：用长连接接收消息，交给 core 里的 Agent 回复"""
import json
import os
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import lark_oapi as lark
from dotenv import load_dotenv
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

from core import aftersales, sales

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

APP_ID = os.getenv("FEISHU_APP_ID")
APP_SECRET = os.getenv("FEISHU_APP_SECRET")

if not APP_ID or not APP_SECRET:
    raise SystemExit("缺少 FEISHU_APP_ID / FEISHU_APP_SECRET，请检查 .env")

_client = lark.Client.builder().app_id(APP_ID).app_secret(APP_SECRET).build()

# 每个会话的状态：open_id -> {"mode": 模式, "history": 对话历史}
SESSIONS = {}
_SESSIONS_LOCK = threading.Lock()

# 同一个用户的消息必须串行处理（否则两条消息会同时改同一份 history），
# 不同用户之间并行。这里给每个用户一把锁。
_USER_LOCKS = {}
_USER_LOCKS_LOCK = threading.Lock()

# 消息幂等去重。用有界 LRU，不用无限增长的 set —— 否则长跑必然吃内存。
# 注意：进程重启后这个表会清空，生产环境建议换成 Redis 之类的持久化去重。
SEEN = OrderedDict()
SEEN_LIMIT = 2000

# 每个会话最多保留多少轮历史（不含 system 提示词）。不截断的话长对话会撑爆上下文。
MAX_HISTORY_TURNS = 12

# 回复要等大模型，耗时数秒。放进线程池，避免一个用户提问把所有其他用户堵住。
_EXECUTOR = ThreadPoolExecutor(max_workers=4)

MODES = {"sales": sales, "aftersales": aftersales}


def resolve_user_id(open_id):
    """把飞书 open_id 映射成业务用户 ID（订单归属校验要用它）。

    真实系统这里要查账号绑定关系；演示环境统一映射到 orders.csv 里的演示用户。
    换成真实映射之后，订单归属校验就能按人工作了。
    """
    return os.getenv("FEISHU_DEMO_USER_ID", "U1001")


def _user_lock(open_id):
    with _USER_LOCKS_LOCK:
        return _USER_LOCKS.setdefault(open_id, threading.Lock())


def _seen(message_id):
    """返回 True 表示这条消息之前已经处理过（飞书会重推）"""
    if message_id in SEEN:
        return True
    SEEN[message_id] = True
    while len(SEEN) > SEEN_LIMIT:
        SEEN.popitem(last=False)
    return False


def _trim(history):
    """只留 system 提示词 + 最近若干轮，避免上下文无限增长"""
    if len(history) > MAX_HISTORY_TURNS + 1:
        del history[1:-MAX_HISTORY_TURNS]


def reply_text(open_id, text):
    """按用户当前模式生成回复"""
    business_user_id = resolve_user_id(open_id)

    with _user_lock(open_id):
        with _SESSIONS_LOCK:
            state = SESSIONS.setdefault(open_id, {"mode": "sales", "history": None})

            if text in ("售后", "转售后"):
                state.update(mode="aftersales", history=None)
                return "已切换到【售后服务】，请问有什么可以帮您？"
            if text in ("售前", "转售前"):
                state.update(mode="sales", history=None)
                return "已切换到【售前导购】，请问有什么可以帮您？"

            module = MODES[state["mode"]]
            if state["history"] is None:
                state["history"] = module.new_history()
            history = state["history"]

        # 调用大模型放在全局锁之外，否则一个用户等回复会堵住其他所有用户
        answer = module.ask(text, history, business_user_id)

        with _SESSIONS_LOCK:
            _trim(history)
    return answer


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


def _handle(open_id, text, chat_id):
    """线程池里执行：生成回复并发回飞书"""
    try:
        answer = reply_text(open_id, text)
    except Exception as e:
        # 单条消息处理失败不能让整个长连接挂掉
        print(f"[错误] 处理消息失败：{type(e).__name__}: {e}")
        answer = "抱歉，我这边出了点小问题，请稍后再试或者联系人工客服～"
    print(f"[回复] {answer}")
    try:
        send_message(chat_id, answer)
    except Exception as e:
        print(f"[错误] 发送失败：{type(e).__name__}: {e}")


def on_message(data):
    """收到飞书消息时的处理"""
    msg = data.event.message
    if _seen(msg.message_id):
        return

    open_id = data.event.sender.sender_id.open_id
    text = json.loads(msg.content).get("text", "").strip()
    text = text.replace("@_user_1", "").strip()  # 群里 @机器人 会带占位符
    if not text:
        return

    print(f"[收到] {text}")
    # 交给线程池：回复要等大模型，不能堵住飞书的事件回调线程
    _EXECUTOR.submit(_handle, open_id, text, msg.chat_id)


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
