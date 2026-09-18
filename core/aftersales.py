import json

from core.retriever import build_context
from core.llm import chat
from core.prompts import AFTERSALES_PROMPT
from core.tools import query_order

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_order",
            "description": "根据订单号查询订单状态、商品、金额和物流信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "订单号，例如 D20250901001",
                    }
                },
                "required": ["order_id"],
            },
        },
    }
]

TOOL_MAP = {"query_order": query_order}


def new_history():
    """开启一段新会话（参考资料每轮再填，所以先留空）"""
    return [{"role": "system", "content": AFTERSALES_PROMPT.format(context="")}]


def ask(question, history):
    """带上下文回答售后问题，模型需要数据时自动调用工具"""
    # 每轮用最新问题重新检索，把知识库资料填进 system 提示词
    history[0] = {
        "role": "system",
        "content": AFTERSALES_PROMPT.format(context=build_context(question)),
    }
    history.append({"role": "user", "content": question})

    while True:
        resp = chat(history, tools=TOOLS)
        msg = resp.choices[0].message

        # 模型没要求调用工具 → 说明这是最终回答
        if not msg.tool_calls:
            history.append({"role": "assistant", "content": msg.content})
            return msg.content

        # 模型要求调用工具 → 我们替它执行
        history.append(msg)
        for call in msg.tool_calls:
            name = call.function.name
            args = json.loads(call.function.arguments)
            result = TOOL_MAP[name](**args)
            history.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, ensure_ascii=False) if result else "未找到该订单",
            })
        # 循环回去，把工具查到的结果交给模型生成回答


if __name__ == "__main__":
    history = new_history()
    for q in [
        "我订单 D20250901001 到哪了？",
        "D20250901002 这个我想退款，能退吗？",
        "帮我查下订单 D9999999",
    ]:
        print("用户：" + q)
        print("客服：" + ask(q, history))
        print("-" * 40)