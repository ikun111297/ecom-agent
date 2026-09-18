"""效果评测：用 LLM 当裁判，判断回答是否准确表达了期望要点"""
from core.llm import chat
from core.sales import ask, new_history

# 正向用例：(问题, 期望要点)
CASES = [
    ("面膜多少钱", "99元"),
    ("精华多少钱", "199元"),
    ("洁面乳多少钱", "59元"),
    ("面膜的规格是多少", "25ml、10片"),
    ("精华适合什么人用", "25岁以上人群"),
    ("洁面乳现在有货吗", "缺货，预计3天补货"),
    ("敏感肌能用面膜吗", "面膜敏感肌可以用"),
    ("孕妇能用精华吗", "孕期不建议用精华"),
    ("精华用多久能看到效果", "建议连续使用4周以上"),
    ("多久能发货", "48小时内发出"),
    ("有什么优惠活动", "满199减20、满299减50"),
    ("怎么退货", "7天无理由退货"),
    ("退款多久到账", "1-3个工作日审核"),
    ("退货运费谁出", "非质量问题的退货由买家承担运费"),
]

# 反向用例：知识库里没有的内容
NEGATIVE = [
    "你们有眼霜吗",
    "帮我推荐一款防晒霜",
]

# 出现这些词，说明模型承认了自己不知道
UNKNOWN_WORDS = ["没有", "不确定", "确认", "查不到", "抱歉", "暂时"]

JUDGE_PROMPT = """你是客服质量评测裁判。
判断【客服回答】是否准确表达了【期望要点】的含义。
同义表达算通过，只要意思对了就算通过。

期望要点：{}
客服回答：{}

只输出"通过"或"不通过"，不要任何解释。"""


def judge(expected, answer):
    """让模型当裁判，判断回答的意思对不对"""
    resp = chat(
        [{"role": "user", "content": JUDGE_PROMPT.format(expected, answer)}],
        temperature=0,
    )
    return "通过" in resp.choices[0].message.content


def main():
    print("=" * 52)
    print("正向测试：回答必须表达期望要点（LLM 裁判）")
    print("=" * 52)

    passed = 0
    for q, expected in CASES:
        ans = ask(q, new_history())
        ok = judge(expected, ans)
        passed += ok
        print(f"[{'OK  ' if ok else 'FAIL'}] {q}")
        if not ok:
            print(f"        期望要点：{expected}")
            print(f"        实际回答：{ans}")
            print(f"        裁判判定：不通过")

    print()
    print("=" * 52)
    print("反向测试：知识库里没有的，不能编")
    print("=" * 52)

    safe = 0
    for q in NEGATIVE:
        ans = ask(q, new_history())
        ok = any(w in ans for w in UNKNOWN_WORDS)
        safe += ok
        print(f"[{'OK  ' if ok else 'FAIL'}] {q}")
        if not ok:
            print(f"        实际回答：{ans}")

    total = len(CASES) + len(NEGATIVE)
    print()
    print("=" * 52)
    print(f"正向准确率：{passed}/{len(CASES)} = {passed / len(CASES):.1%}")
    print(f"幻觉拦截率：{safe}/{len(NEGATIVE)} = {safe / len(NEGATIVE):.1%}")
    print(f"综合得分：  {passed + safe}/{total} = {(passed + safe) / total:.1%}")
    print("=" * 52)


if __name__ == "__main__":
    main()