
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

UA = {"User-Agent": "CompetitorWatch/1.0 (+https://github.com/)"}
PRICE_RE = re.compile(r"(\d+[.,]?\d*)")

def fetch_generic_catalog(site_cfg: dict, global_cfg: dict):
    timeout = int(global_cfg.get("schedule", {}).get("request_timeout_sec", 20))
    max_products = int(global_cfg.get("schedule", {}).get("max_products_per_site", 800))

    products = []
    meta = {"mode": "generic"}

    cats = site_cfg.get("categories", [])
    base_url = site_cfg["base_url"].rstrip("/")

    for c in cats:
        url = c.get("url")
        if not url:
            continue
        r = requests.get(url, timeout=timeout, headers=UA)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        links = []
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not href:
                continue
            full = urljoin(url, href)
            if any(x in full for x in ["/products/", "/product/", "/item/"]):
                links.append(full)

        seen = set()
        links = [x for x in links if not (x in seen or seen.add(x))]

        for product_url in links[:max_products]:
            try:
                pr = requests.get(product_url, timeout=timeout, headers=UA)
                pr.raise_for_status()
                ps = BeautifulSoup(pr.text, "lxml")
                title = (ps.select_one("meta[property='og:title']") or ps.select_one("title"))
                title_text = title.get("content").strip() if title and title.has_attr("content") else (title.text.strip() if title else "")

                price = None
                ogp = ps.select_one("meta[property='product:price:amount']")
                if ogp and ogp.get("content"):
                    try:
                        price = float(ogp["content"])
                    except Exception:
                        pass
                if price is None:
                    text = ps.get_text(" ", strip=True)
                    m = PRICE_RE.search(text)
                    if m:
                        try:
                            price = float(m.group(1).replace(",", ""))
                        except Exception:
                            pass

                key = f"generic:{product_url}"
                products.append({
                    "key": key,
                    "title": title_text,
                    "variant_label": "",
                    "min_price": price,
                    "max_price": price,
                    "currency": None,
                    "available": True,
                    "product_url": product_url,
                    "category": c.get("label", "Category"),
                    "published_at": None,
                    "updated_at": None,
                })
            except Exception:
                continue

    return {"products": products, "meta": meta}

