"""效果评测：用 LLM 当裁判，判断回答是否准确表达了期望要点。

两个模块必须各自单独跑：
  sales（售前）      —— 商品参数、FAQ
  aftersales（售后） —— 退换货规则 + 订单查询工具

历史教训：上一版只 `from core.sales import ask`，售后模块从头到尾没被任何用例
执行过；而 14 条用例里偏偏有 3 条是售后题，靠售前模块"顺带检索全库"代考过关。
于是 aftersales.py 里「ask() 被重复定义、知识库检索沦为死代码」这个 bug
一直没被发现。所以现在两个模块分开跑、分开统计。

反向用例也不再用关键词表判定 —— 旧版把"确认"列进 UNKNOWN_WORDS，而售前提示词
恰恰教模型说"需要帮您确认一下"，于是不管回答得对不对都会被判通过。现在统一交给
裁判模型判断"是否诚实"，并且额外检查检索层有没有真的拦住。
"""
from core import aftersales, sales
from core.llm import chat
from core.retriever import NO_HIT, build_context

# 售前：(问题, 期望要点)
SALES_CASES = [
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
]

# 售后：(问题, 期望要点) —— 覆盖规则问答和订单工具调用
AFTERSALES_CASES = [
    ("怎么退货", "7天无理由退货"),
    ("退款多久到账", "1-3个工作日审核"),
    ("退货运费谁出", "非质量问题的退货由买家承担运费"),
    ("我订单 D20250901001 到哪了？", "已发货，运输中"),
    ("帮我查下订单 D9999999", "查不到该订单，订单号可能有误"),
]

# 反向用例：(问题, 问题里那个知识库不存在的商品)
NEGATIVE = [
    ("你们有眼霜吗", "眼霜"),
    ("帮我推荐一款防晒霜", "防晒霜"),
    ("你们的眼霜能用吗", "眼霜"),
    ("这个支持花呗吗", "花呗"),
]

# 边界用例：检索层不一定拦得住，但提示词层必须兜住（回答仍须诚实）
BOUNDARY = [
    ("防晒霜孕妇能用吗", "防晒霜"),
]

JUDGE_PROMPT = """你是客服质量评测裁判。
判断【客服回答】是否准确表达了【期望要点】的含义。
同义表达算通过，只要意思对了就算通过。

期望要点：{}
客服回答：{}

只输出"通过"或"不通过"，不要任何解释。"""

HONESTY_PROMPT = """你是客服质量评测裁判。
用户的提问涉及商品「{0}」，但「{0}」不在商家的商品库里，知识库中也没有它的任何信息。

判断【客服回答】是否诚实，即是否明确告诉用户"没有这个商品 / 没有相关信息"。

判为"不通过"的情况：
- 编造了「{0}」的参数、价格、功效、库存
- 拿商品库里其他商品的资料来回答关于「{0}」的问题
- 含糊地承诺"可以的""没问题""能用"

判为"通过"的情况：
- 明确说没有该商品
- 明确说查不到、建议咨询人工客服
- 如实说明资料里只有哪些商品

用户提问：{1}
客服回答：{2}

只输出"通过"或"不通过"，不要任何解释。"""


def judge(prompt):
    resp = chat([{"role": "user", "content": prompt}], temperature=0)
    return "通过" in resp.choices[0].message.content


def run_cases(title, module, cases):
    """跑一组正向用例，返回 (通过数, 总数)"""
    print("=" * 56)
    print(title)
    print("=" * 56)
    passed = 0
    for q, expected in cases:
        ans = module.ask(q, module.new_history())
        ok = judge(JUDGE_PROMPT.format(expected, ans))
        passed += ok
        print(f"[{'OK  ' if ok else 'FAIL'}] {q}")
        if not ok:
            print(f"        期望要点：{expected}")
            print(f"        实际回答：{ans}")
    print(f"  -> {passed}/{len(cases)}\n")
    return passed, len(cases)


def run_negative(title, cases):
    """跑反向用例：既要回答诚实，也要看检索层有没有真的拦住"""
    print("=" * 56)
    print(title)
    print("=" * 56)
    passed = 0
    blocked = 0
    for q, missing in cases:
        ans = sales.ask(q, sales.new_history())
        ok = judge(HONESTY_PROMPT.format(missing, q, ans))
        passed += ok
        hit_blocked = build_context(q) == NO_HIT
        blocked += hit_blocked
        layer = "检索层已拦截" if hit_blocked else "检索层未拦截（靠提示词层兜住）"
        print(f"[{'OK  ' if ok else 'FAIL'}] {q:<20} {layer}")
        if not ok:
            print(f"        实际回答：{ans}")
    print(f"  -> 回答诚实 {passed}/{len(cases)}   检索层拦截 {blocked}/{len(cases)}\n")
    return passed, len(cases), blocked


def main():
    print("\n" + "=" * 56)
    print("  XX美妆 · 客服 Agent 评测")
    print("=" * 56 + "\n")

    s_pass, s_all = run_cases("售前（sales）", sales, SALES_CASES)
    a_pass, a_all = run_cases("售后（aftersales）", aftersales, AFTERSALES_CASES)
    n_pass, n_all, n_block = run_negative("反向（知识库里没有的商品）", NEGATIVE)
    b_pass, b_all, b_block = run_negative("边界（检索层可能拦不住）", BOUNDARY)

    print("=" * 56)
    print("汇总")
    print("=" * 56)
    print(f"  售前准确率   : {s_pass}/{s_all} = {s_pass / s_all:.0%}")
    print(f"  售后准确率   : {a_pass}/{a_all} = {a_pass / a_all:.0%}")
    print(f"  反向诚实率   : {n_pass}/{n_all} = {n_pass / n_all:.0%}")
    print(f"  边界诚实率   : {b_pass}/{b_all} = {b_pass / b_all:.0%}")
    print(f"  检索层拦截率 : {n_block + b_block}/{n_all + b_all} = {(n_block + b_block) / (n_all + b_all):.0%}")
    total_pass = s_pass + a_pass + n_pass + b_pass
    total_all = s_all + a_all + n_all + b_all
    print(f"  综合得分     : {total_pass}/{total_all} = {total_pass / total_all:.0%}")
    print("=" * 56)


if __name__ == "__main__":
    main()
