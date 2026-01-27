
import requests
from urllib.parse import urlparse

def _get_json(url, timeout=20):
    r = requests.get(url, timeout=timeout, headers={
        "User-Agent": "CompetitorWatch/1.0 (+https://github.com/)"
    })
    r.raise_for_status()
    return r.json()

def _collection_handle_from_url(url: str):
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "collections":
        return parts[1]
    return None

def try_fetch_shopify(site_cfg: dict, global_cfg: dict):
    base = site_cfg["base_url"].rstrip("/")
    timeout = int(global_cfg.get("schedule", {}).get("request_timeout_sec", 20))
    max_products = int(global_cfg.get("schedule", {}).get("max_products_per_site", 800))

    products = []
    meta = {"mode": "shopify"}
    bestsellers = _try_fetch_bestsellers(base, timeout=timeout, limit=20)

    cats = site_cfg.get("categories", [])
    if cats:
        seen = set()
        for c in cats:
            handle = _collection_handle_from_url(c.get("url", ""))
            if not handle:
                continue
            page = 1
            while True:
                url = f"{base}/collections/{handle}/products.json?limit=250&page={page}"
                data = _get_json(url, timeout=timeout)
                batch = data.get("products", [])
                if not batch:
                    break
                for p in batch:
                    norm = _normalize_shopify_product(base, p, site_cfg, category_label=c.get("label", handle))
                    if norm["key"] in seen:
                        continue
                    seen.add(norm["key"])
                    products.append(norm)
                    if len(products) >= max_products:
                        return {"products": products, "meta": meta, "bestsellers": bestsellers}
                page += 1
    else:
        page = 1
        while True:
            url = f"{base}/products.json?limit=250&page={page}"
            data = _get_json(url, timeout=timeout)
            batch = data.get("products", [])
            if not batch:
                break
            for p in batch:
                products.append(_normalize_shopify_product(base, p, site_cfg, category_label="All"))
                if len(products) >= max_products:
                    return {"products": products, "meta": meta, "bestsellers": bestsellers}
            page += 1

    return {"products": products, "meta": meta, "bestsellers": bestsellers}

def _pick_variant_label(variant):
    title = (variant.get("title") or "").strip()
    if title and title.lower() != "default title":
        return title
    return ""

def _normalize_shopify_product(base_url, p: dict, site_cfg: dict, category_label: str):
    handle = p.get("handle", "")
    product_url = f"{base_url}/products/{handle}" if handle else base_url
    title = (p.get("title") or "").strip()

    prices = []
    variants = p.get("variants", []) or []
    for v in variants:
        try:
            prices.append(float(v.get("price")))
        except Exception:
            pass
    min_price = min(prices) if prices else None
    max_price = max(prices) if prices else None

    available = any(bool(v.get("available")) for v in variants) if variants else True

    variant_label = ""
    for v in variants:
        if v.get("available"):
            variant_label = _pick_variant_label(v)
            break
    if not variant_label and variants:
        variant_label = _pick_variant_label(variants[0])

    key = f"shopify:{handle}" if handle else f"shopify:id:{p.get('id')}"

    return {
        "key": key,
        "title": title,
        "variant_label": variant_label,
        "min_price": min_price,
        "max_price": max_price,
        "currency": None,
        "available": available,
        "product_url": product_url,
        "category": category_label,
        "published_at": p.get("published_at"),
        "updated_at": p.get("updated_at"),
    }

def _try_fetch_bestsellers(base: str, timeout: int = 20, limit: int = 20):
    """
    Best effort: attempt common Shopify bestsellers collection handles.
    """
    candidate_handles = [
        "bestsellers",
        "best-sellers",
        "best-selling",
        "best-selling-products",
        "top-sellers",
        "trending",
    ]

    for h in candidate_handles:
        url = f"{base}/collections/{h}/products.json?limit={limit}&page=1"
        try:
            data = _get_json(url, timeout=timeout)
            batch = data.get("products", []) or []
            if not batch:
                continue
            out = []
            for p in batch:
                out.append(
                    _normalize_shopify_product(
                        base, p, {}, category_label="Bestsellers"
                    )
                )
            return out
        except Exception:
            continue

    return []