"""KPIダッシュボード・売上レポートコマンド

Shopify注文データを集計し収益KPIを可視化する。

使い方:
  python shopify_manager.py kpi --period 30       # 過去30日
  python shopify_manager.py kpi --period 7 --ai   # AI分析付き
  python shopify_manager.py kpi --output kpi.csv  # CSV出力
"""

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shopify_client import ShopifyClient
from utils.logger import setup_logger

logger = setup_logger(__name__)

TARGET_MONTHLY_REVENUE = 1_000_000  # 月100万円目標


def run_kpi_dashboard(
    client: ShopifyClient,
    period_days: int = 30,
    output_path: str | None = None,
    use_ai: bool = False,
) -> dict:
    logger.info(f"過去{period_days}日間のKPIを集計中...")

    since = (datetime.now(timezone.utc) - timedelta(days=period_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    orders = client.get_orders(since=since)
    products = client.get_all_products({"status": "active"})

    kpi = _calculate_kpi(orders, products, period_days)
    _print_dashboard(kpi, period_days)

    if output_path:
        _export_csv(orders, kpi, output_path)
        logger.info(f"KPIデータを {output_path} に出力しました")

    if use_ai:
        _ai_analysis(kpi, orders)

    return kpi


def _calculate_kpi(orders: list[dict], products: list[dict], period_days: int) -> dict:
    paid_orders = [o for o in orders if o.get("financial_status") == "paid"]

    total_revenue = sum(float(o.get("total_price", 0)) for o in paid_orders)
    order_count = len(paid_orders)
    aov = total_revenue / order_count if order_count else 0

    # 商品別売上
    product_sales: dict[str, dict] = {}
    for order in paid_orders:
        for item in order.get("line_items", []):
            pid = str(item.get("product_id", "unknown"))
            title = item.get("title", "不明")
            qty = item.get("quantity", 1)
            price = float(item.get("price", 0))
            if pid not in product_sales:
                product_sales[pid] = {"title": title, "qty": 0, "revenue": 0.0}
            product_sales[pid]["qty"] += qty
            product_sales[pid]["revenue"] += qty * price

    top_products = sorted(product_sales.values(), key=lambda x: x["revenue"], reverse=True)[:5]

    # 月換算・目標達成率
    monthly_projected = total_revenue * (30 / period_days) if period_days != 30 else total_revenue
    goal_rate = monthly_projected / TARGET_MONTHLY_REVENUE * 100

    # リピート率（同一メールで2件以上）
    email_counts: dict[str, int] = {}
    for o in paid_orders:
        email = o.get("email", "")
        if email:
            email_counts[email] = email_counts.get(email, 0) + 1
    repeat_customers = sum(1 for c in email_counts.values() if c > 1)
    repeat_rate = repeat_customers / len(email_counts) * 100 if email_counts else 0

    return {
        "period_days": period_days,
        "total_revenue": total_revenue,
        "order_count": order_count,
        "aov": aov,
        "monthly_projected": monthly_projected,
        "goal_rate": goal_rate,
        "repeat_rate": repeat_rate,
        "active_products": len(products),
        "top_products": top_products,
        "daily_avg_revenue": total_revenue / period_days if period_days else 0,
        "daily_avg_orders": order_count / period_days if period_days else 0,
    }


def _print_dashboard(kpi: dict, period_days: int) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    goal = kpi["goal_rate"]
    bar = "█" * int(goal / 5) + "░" * (20 - int(goal / 5))
    bar = bar[:20]

    logger.info("=" * 60)
    logger.info(f"  KPIダッシュボード  {now}")
    logger.info(f"  集計期間: 過去{period_days}日間")
    logger.info("=" * 60)
    logger.info(f"  売上合計        : ¥{kpi['total_revenue']:>12,.0f}")
    logger.info(f"  注文件数        : {kpi['order_count']:>10}件")
    logger.info(f"  平均注文単価    : ¥{kpi['aov']:>12,.0f}")
    logger.info(f"  日次平均売上    : ¥{kpi['daily_avg_revenue']:>12,.0f}")
    logger.info(f"  月次換算売上    : ¥{kpi['monthly_projected']:>12,.0f}")
    logger.info(f"  リピート率      : {kpi['repeat_rate']:>9.1f}%")
    logger.info(f"  公開商品数      : {kpi['active_products']:>10}件")
    logger.info("-" * 60)
    logger.info(f"  月100万目標達成率: {goal:.1f}%")
    logger.info(f"  [{bar}]")
    gap = TARGET_MONTHLY_REVENUE - kpi["monthly_projected"]
    if gap > 0:
        daily_needed = gap / 30
        logger.info(f"  目標まであと    : ¥{gap:>12,.0f}")
        logger.info(f"  必要な日次追加  : ¥{daily_needed:>12,.0f}")
    else:
        logger.info("  目標達成！")
    logger.info("-" * 60)
    if kpi["top_products"]:
        logger.info("  売れ筋TOP5:")
        for i, p in enumerate(kpi["top_products"], 1):
            logger.info(f"    {i}. {p['title'][:30]:30s} ¥{p['revenue']:>8,.0f} ({p['qty']}件)")
    logger.info("=" * 60)


def _export_csv(orders: list[dict], kpi: dict, output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for order in orders:
        if order.get("financial_status") != "paid":
            continue
        for item in order.get("line_items", []):
            rows.append({
                "order_id": order.get("id"),
                "created_at": order.get("created_at"),
                "email": order.get("email", ""),
                "product_title": item.get("title"),
                "quantity": item.get("quantity"),
                "price": item.get("price"),
                "total": float(item.get("price", 0)) * item.get("quantity", 1),
            })

    if rows:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    # KPIサマリーも別ファイルに
    summary_path = path.with_suffix(".summary.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"KPIサマリー {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        for k, v in kpi.items():
            if k != "top_products":
                f.write(f"{k}: {v}\n")


def _ai_analysis(kpi: dict, orders: list[dict]) -> None:
    try:
        from utils.ai_client import _get_client

        summary = {
            "monthly_projected": kpi["monthly_projected"],
            "goal_rate": kpi["goal_rate"],
            "aov": kpi["aov"],
            "order_count": kpi["order_count"],
            "repeat_rate": kpi["repeat_rate"],
            "top_products": kpi["top_products"][:3],
        }

        prompt = f"""Shopifyストアの売上KPIを分析し、月100万円達成に向けた具体的な改善提案を3つ提示してください。

KPIデータ:
{summary}

出力形式:
【現状分析】（2文）
【改善提案1】タイトル: 内容
【改善提案2】タイトル: 内容
【改善提案3】タイトル: 内容
【今週やること】（最優先アクション1つ）"""

        resp = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        analysis = resp.content[0].text.strip()
        logger.info("\n[AI分析]\n" + analysis)
    except Exception as e:
        logger.warning(f"AI分析失敗: {e}")
