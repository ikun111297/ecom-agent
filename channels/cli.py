"""命令行渠道：只负责跟用户打交道，不含任何业务逻辑"""
import os

from core import aftersales, sales

MODULES = {
    "1": ("售前导购", sales),
    "2": ("售后服务", aftersales),
}

# 演示用身份。真实系统里它来自登录态；命令行没有登录，所以用环境变量指定
# （默认 U1001 —— orders.csv 里属于该用户的演示订单）。
DEMO_USER_ID = os.getenv("DEMO_USER_ID", "U1001")


def chat_loop(name, module):
    """一轮对话。返回 True 表示用户要退出程序"""
    print(f"\n--- {name}（返回：回主菜单 | 退出：结束程序）---")
    print(f"（当前身份：{DEMO_USER_ID}，改身份请设置环境变量 DEMO_USER_ID）")
    history = module.new_history()

    while True:
        q = input("\n你：").strip()
        if not q:
            continue
        if q in ("退出", "exit", "q"):
            return True
        if q in ("返回", "back"):
            return False
        if q == "重来":
            history = module.new_history()
            print("（已开启新会话）")
            continue
        print("\n客服：" + module.ask(q, history, DEMO_USER_ID))


def main():
    print("=" * 44)
    print("   XX美妆 · 智能客服")
    print("=" * 44)

    while True:
        print("\n请选择服务：  1 售前导购    2 售后服务    0 退出")
        pick = input("输入数字：").strip()

        if pick == "0":
            break
        if pick not in MODULES:
            print("请输入 0 / 1 / 2")
            continue

        name, module = MODULES[pick]
        if chat_loop(name, module):
            break

    print("再见～")


if __name__ == "__main__":
    main()