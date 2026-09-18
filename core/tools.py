import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORDERS_FILE = ROOT / "data" / "orders.csv"

# 不返回给模型的字段：客户姓名是个人信息，客服回答里用不到，干脆不给模型，避免被念出来
PRIVATE_FIELDS = {"customer", "user_id"}


def _find(order_id):
    with open(ORDERS_FILE, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["order_id"] == order_id:
                return row
    return None


def query_order(order_id, user_id=None):
    """按订单号查订单。

    返回结构化结果，让模型分得清「单号不存在」和「无权查看」两种情况。

    user_id 由渠道层注入、并覆盖模型自己传的任何值 —— 模型无法伪造身份。
    没有这道校验时，任何人只要输入别人的订单号就能拿到别人的订单明细。
    """
    row = _find(order_id)
    if row is None:
        return {"found": False, "reason": "订单号不存在，请用户核对订单号"}

    if user_id is not None and row.get("user_id") != user_id:
        return {"found": False, "reason": "该订单不属于当前用户，无法查询，建议转人工客服"}

    order = {k: v for k, v in row.items() if k not in PRIVATE_FIELDS}
    return {"found": True, "order": order}


if __name__ == "__main__":
    print(query_order("D20250901001", "U1001"))  # 本人订单 -> 正常返回
    print(query_order("D20250901002", "U1001"))  # 别人的订单 -> 拒绝
    print(query_order("D9999999", "U1001"))      # 不存在 -> 拒绝
    print(query_order("D20250901001"))           # 不带身份（内部调试）-> 不校验归属
