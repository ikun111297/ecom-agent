from core.llm import chat
from core.prompts import SALES_PROMPT
from core.retriever import build_context


def new_history():
    """开启一段新会话（参考资料每轮再填，所以先留空）"""
    return [{"role": "system", "content": SALES_PROMPT.format(context="")}]


def ask(question, history, user_id=None):
    """先检索，再带着检索结果回答。

    user_id 在售前用不到（不涉及订单归属），保留它只为和售后模块保持同样的签名，
    这样渠道层可以统一调用 module.ask(question, history, user_id)，不用分支判断。
    """
    # 用最新问题重写 system 提示词，把检索到的资料填进去
    history[0] = {
        "role": "system",
        "content": SALES_PROMPT.format(context=build_context(question)),
    }

    history.append({"role": "user", "content": question})
    resp = chat(history)
    msg = resp.choices[0].message
    history.append({"role": "assistant", "content": msg.content})
    return msg.content