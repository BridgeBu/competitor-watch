import os
import time
from datetime import datetime, timezone
import yaml

from fetchers.shopify import try_fetch_shopify
from fetchers.generic import fetch_generic_catalog
from storage import load_latest_snapshot, load_snapshot_days_ago, save_snapshot, prune_snapshots, write_json
from diff import diff_snapshots
from report import build_summary

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DATA = os.path.join(ROOT, "docs", "data")
SNAP_DIR = os.path.join(DOCS_DATA, "snapshots")

def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def load_config():
    with open(os.path.join(ROOT, "config.yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def ensure_dirs():
    os.makedirs(DOCS_DATA, exist_ok=True)
    os.makedirs(SNAP_DIR, exist_ok=True)



def _group_products_by_category(products, currency_symbol):
    """
    为了前端展示：按 category 分组，同时保留关键字段
    注意：不要把整个 Shopify 原始结构塞进去，否则 sites.json 会非常大
    """
    by = {}
    for p in products or []:
        cat = p.get("category") or "Other"
        by.setdefault(cat, [])
        by[cat].append({
            "key": p.get("key"),
            "title": p.get("title"),
            "variant_label": p.get("variant_label") or "",
            "min_price": p.get("min_price"),
            "max_price": p.get("max_price"),
            "available": p.get("available"),
            "url": p.get("product_url"),
        })

    # 每个分类内部按价格排序（更好读）
    for cat, items in by.items():
        items.sort(key=lambda x: (x["min_price"] is None, x["min_price"] or 0, x["title"] or ""))

    return by

def _bucketize(price, buckets):
    # buckets: [(0,50),(50,100)..., (200,None)]
    for lo, hi in buckets:
        if price is None:
            return None
        if hi is None and price >= lo:
            return f"{lo}+"
        if hi is not None and lo <= price < hi:
            return f"{lo}-{hi}"
    return None


def _compute_price_buckets(products):
    # 用 min_price 做统计（对区间更稳定）
    buckets = [(0, 50), (50, 100), (100, 150), (150, 200), (200, None)]
    total = {"0-50": 0, "50-100": 0, "100-150": 0, "150-200": 0, "200+": 0}
    by_cat = {}
    for p in products:
        cat = p.get("category") or "Other"
        by_cat.setdefault(cat, {"0-50": 0, "50-100": 0, "100-150": 0, "150-200": 0, "200+": 0})
        price = p.get("min_price")
        key = _bucketize(price, buckets)
        if key == "0-50":
            total["0-50"] += 1;
            by_cat[cat]["0-50"] += 1
        elif key == "50-100":
            total["50-100"] += 1;
            by_cat[cat]["50-100"] += 1
        elif key == "100-150":
            total["100-150"] += 1;
            by_cat[cat]["100-150"] += 1
        elif key == "150-200":
            total["150-200"] += 1;
            by_cat[cat]["150-200"] += 1
        elif key == "200+":
            total["200+"] += 1;
            by_cat[cat]["200+"] += 1
    sku_by_cat = {}
    for p in products:
        cat = p.get("category") or "Other"
        sku_by_cat[cat] = sku_by_cat.get(cat, 0) + 1
    return total, by_cat, sku_by_cat


def run_once():
    ensure_dirs()
    cfg = load_config()
    run_id = utc_now_iso().replace(":", "-")
    errors = []
    site_results = []

    for site in cfg.get("sites", []):
        site_id = site["id"]
        name = site.get("name", site_id)
        base_url = site["base_url"].rstrip("/")
        retries = int(site.get("retries", 1))

        baseline_days = cfg.get("schedule", {}).get("baseline_days", 3)
        baseline = load_snapshot_days_ago(SNAP_DIR, site_id, days=baseline_days)
        baseline_products = baseline.get("products", []) if baseline else []
        baseline_time_utc = baseline.get("time_utc") if baseline else None

        fetched = None
        last_err = None

        # 1) Shopify first (best effort)
        for attempt in range(retries + 1):
            try:
                fetched = try_fetch_shopify(site, cfg)
                if fetched and fetched.get("products"):
                    break
            except Exception as e:
                last_err = str(e)
                fetched = None
            time.sleep(0.8)

        # 2) Fallback: generic fetcher (best effort)
        if not fetched or not fetched.get("products"):
            for attempt in range(retries + 1):
                try:
                    fetched = fetch_generic_catalog(site, cfg)
                    if fetched and fetched.get("products"):
                        break
                except Exception as e:
                    last_err = str(e)
                    fetched = None
                time.sleep(0.8)

        if not fetched or not fetched.get("products"):
            # Fail-safe: do not overwrite snapshots; record error only
            err = {
                "site_id": site_id,
                "name": name,
                "base_url": base_url,
                "run_id": run_id,
                "time_utc": utc_now_iso(),
                "error": last_err or "Fetch failed (no products)",
            }
            errors.append(err)

            site_results.append({
                "site_id": site_id,
                "name": name,
                "base_url": base_url,
                "status": "error",
                "error": err["error"],
                "changes": [],
                "counts": {"new": 0, "removed": 0, "price": 0, "restock": 0, "oos": 0},
                "baseline_days": baseline_days,
                "baseline_time_utc": baseline_time_utc,
            })
            continue

        snapshot = {
            "site_id": site_id,
            "name": name,
            "base_url": base_url,
            "run_id": run_id,
            "time_utc": utc_now_iso(),
            "products": fetched["products"],
            "meta": fetched.get("meta", {}),
            "bestsellers": fetched.get("bestsellers", []),
        }

        currency_symbol = site.get("currency_symbol") or "€"
        currency_code = site.get("currency_code") or "EUR"

        pb_total, pb_by_cat, sku_by_cat = _compute_price_buckets(snapshot["products"])

        save_snapshot(SNAP_DIR, site_id, snapshot)

        changes, counts = diff_snapshots(baseline_products, snapshot["products"])

        # 商品状态统计（总SKU/在架/缺货）
        total_sku = len(snapshot["products"])
        in_stock = sum(1 for p in snapshot["products"] if p.get("available") is True)
        oos = sum(1 for p in snapshot["products"] if p.get("available") is False)

        product_status = {
            "total": total_sku,
            "in_stock": in_stock,
            "oos": oos,
        }

        bestsellers_items = []
        for p in (snapshot.get("bestsellers") or [])[:20]:
            bestsellers_items.append({
                "title": p.get("title"),
                "variant_label": p.get("variant_label") or "",
                "min_price": p.get("min_price"),
                "max_price": p.get("max_price"),
                "available": p.get("available"),
                "url": p.get("product_url"),
            })

        site_results.append({
            "site_id": site_id,
            "name": name,
            "base_url": base_url,
            "status": "ok",
            "error": "",
            "currency_symbol": currency_symbol,
            "currency_code": currency_code,
            "changes": changes,
            "counts": counts,
            "baseline_days": baseline_days,
            "baseline_time_utc": baseline_time_utc,
            "sku_by_category": sku_by_cat,
            "price_buckets_total": pb_total,
            "price_buckets_by_category": pb_by_cat,
            "products_by_category": _group_products_by_category(snapshot["products"], currency_symbol),
            "product_total": len(snapshot["products"]),
            "product_status": product_status,
            "bestsellers": bestsellers_items,
        })

    keep = int(cfg.get("schedule", {}).get("keep_snapshots", 40))
    prune_snapshots(SNAP_DIR, keep_per_site=keep)

    summary = build_summary(site_results, run_id=run_id, time_utc=utc_now_iso())

    write_json(os.path.join(DOCS_DATA, "summary.json"), summary)
    write_json(os.path.join(DOCS_DATA, "sites.json"), site_results)
    write_json(os.path.join(DOCS_DATA, "errors.json"), errors)

    print("Done. Sites:", len(site_results), "Errors:", len(errors))

if __name__ == "__main__":
    run_once()
