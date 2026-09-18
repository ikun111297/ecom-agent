import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORDERS_FILE = ROOT / "data" / "orders.csv"


def query_order(order_id):
    """按订单号查订单，查到返回字典，查不到返回 None"""
    with open(ORDERS_FILE, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["order_id"] == order_id:
                return row
    return None


if __name__ == "__main__":
    print(query_order("D20250901001"))
    print(query_order("D20250901002"))
    print(query_order("D9999999"))