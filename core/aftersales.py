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


# 工具调用最多几轮。模型万一陷入反复调工具的循环，靠这个兜住，不至于无限请求 API
MAX_TOOL_STEPS = 5


def ask(question, history, user_id=None):
    """带上下文回答售后问题，模型需要数据时自动调用工具。

    user_id 由渠道层传入（飞书用 open_id、命令行用演示身份），用于校验订单归属。
    模型无法伪造这个值 —— 它由系统注入，并覆盖模型自己传的任何 user_id。
    """
    # 每轮用最新问题重新检索，把知识库资料填进 system 提示词
    history[0] = {
        "role": "system",
        "content": AFTERSALES_PROMPT.format(context=build_context(question)),
    }
    history.append({"role": "user", "content": question})

    for _ in range(MAX_TOOL_STEPS):
        resp = chat(history, tools=TOOLS)
        msg = resp.choices[0].message

        # 模型没要求调用工具 → 说明这是最终回答
        if not msg.tool_calls:
            history.append({"role": "assistant", "content": msg.content})
            return msg.content

        # 模型要求调用工具 → 我们替它执行
        history.append(msg)
        for call in msg.tool_calls:
            history.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": run_tool(call, user_id),
            })
        # 循环回去，把工具查到的结果交给模型生成回答

    # 轮次用完还没给出结论：兜一句，别让用户空等
    return "抱歉，这个问题我这边暂时处理不了，建议您转人工客服进一步核实。"


def run_tool(call, user_id):
    """执行模型请求的工具调用。

    任何异常都转成结构化结果还给模型，而不是直接抛出去让整段对话崩掉。
    user_id 强制覆盖模型传参：身份只能由渠道层决定，不能由模型自己声明。
    """
    name = call.function.name
    fn = TOOL_MAP.get(name)
    if fn is None:
        return json.dumps({"error": f"未知工具：{name}"}, ensure_ascii=False)

    try:
        args = json.loads(call.function.arguments or "{}")
    except json.JSONDecodeError:
        return json.dumps({"error": "工具参数不是合法 JSON"}, ensure_ascii=False)

    if not isinstance(args, dict):
        return json.dumps({"error": "工具参数格式错误"}, ensure_ascii=False)

    if name == "query_order":
        args["user_id"] = user_id

    try:
        result = fn(**args)
    except TypeError as e:
        return json.dumps({"error": f"工具参数不匹配：{e}"}, ensure_ascii=False)

    return json.dumps(result, ensure_ascii=False)


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