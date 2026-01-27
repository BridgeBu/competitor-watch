import os, textwrap

FILES = {
  "requirements.txt": """\
requests==2.32.3
PyYAML==6.0.2
beautifulsoup4==4.12.3
lxml==5.2.2
""",
  "README.md": """\
# Competitor Watch

A lightweight competitor product monitor (new / price change / removed / stock) that runs on GitHub Actions
and publishes a dashboard via GitHub Pages.

## Quick start
1) Edit config.yaml
2) python -m venv .venv && source .venv/bin/activate
3) pip install -r requirements.txt
4) python src/run.py
5) Open docs/index.html (or deploy GitHub Pages)
""",
  "config.yaml": """\
schedule:
  keep_snapshots: 40
  max_products_per_site: 800
  request_timeout_sec: 20

sites:
  - id: "brand_a"
    name: "Brand A"
    base_url: "https://example-a.com"
    categories:
      - label: "Earrings"
        url: "https://example-a.com/collections/earrings"
    variant_name_priority:
      - "Material"
      - "Finish"
      - "Color"
    retries: 2
""",
  "src/run.py": """\
<REPLACE_WITH_RUN_PY>
""",
  "src/diff.py": """\
<REPLACE_WITH_DIFF_PY>
""",
  "src/storage.py": """\
<REPLACE_WITH_STORAGE_PY>
""",
  "src/report.py": """\
<REPLACE_WITH_REPORT_PY>
""",
  "src/fetchers/__init__.py": "",
  "src/fetchers/shopify.py": """\
<REPLACE_WITH_SHOPIFY_PY>
""",
  "src/fetchers/generic.py": """\
<REPLACE_WITH_GENERIC_PY>
""",
  "docs/index.html": """\
<REPLACE_WITH_INDEX_HTML>
""",
  "docs/app.js": """\
<REPLACE_WITH_APP_JS>
""",
  "docs/style.css": """\
<REPLACE_WITH_STYLE_CSS>
""",
  ".github/workflows/watch.yml": """\
<REPLACE_WITH_WORKFLOW_YML>
""",
  "docs/data/.gitkeep": ""
}

# --- Paste the real file contents here ---
REPLACEMENTS = {
  "<REPLACE_WITH_RUN_PY>": r'''
import os
import time
from datetime import datetime, timezone
import yaml

from fetchers.shopify import try_fetch_shopify
from fetchers.generic import fetch_generic_catalog
from storage import load_latest_snapshot, save_snapshot, prune_snapshots, write_json
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

        last = load_latest_snapshot(SNAP_DIR, site_id)
        last_products = last.get("products", []) if last else []

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
        }

        save_snapshot(SNAP_DIR, site_id, snapshot)

        changes, counts = diff_snapshots(last_products, snapshot["products"])

        site_results.append({
            "site_id": site_id,
            "name": name,
            "base_url": base_url,
            "status": "ok",
            "error": "",
            "changes": changes,
            "counts": counts,
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
''',

  "<REPLACE_WITH_DIFF_PY>": r'''
def _index(products):
    return {p["key"]: p for p in (products or [])}

def _price_repr(p):
    return (p.get("min_price"), p.get("max_price"))

def diff_snapshots(prev_products, cur_products):
    prev = _index(prev_products)
    cur = _index(cur_products)

    changes = []
    counts = {"new": 0, "removed": 0, "price": 0, "restock": 0, "oos": 0}

    for k, now in cur.items():
        old = prev.get(k)
        if not old:
            counts["new"] += 1
            changes.append({
                "type": "NEW",
                "title": now.get("title"),
                "variant_label": now.get("variant_label", ""),
                "category": now.get("category", ""),
                "old_price": None,
                "new_price": _price_repr(now),
                "available_before": None,
                "available_now": now.get("available"),
                "url": now.get("product_url"),
                "key": k,
            })
            continue

        if _price_repr(old) != _price_repr(now):
            counts["price"] += 1
            changes.append({
                "type": "PRICE",
                "title": now.get("title"),
                "variant_label": now.get("variant_label", ""),
                "category": now.get("category", ""),
                "old_price": _price_repr(old),
                "new_price": _price_repr(now),
                "available_before": old.get("available"),
                "available_now": now.get("available"),
                "url": now.get("product_url"),
                "key": k,
            })

        if old.get("available") and not now.get("available"):
            counts["oos"] += 1
            changes.append({
                "type": "OOS",
                "title": now.get("title"),
                "variant_label": now.get("variant_label", ""),
                "category": now.get("category", ""),
                "old_price": _price_repr(old),
                "new_price": _price_repr(now),
                "available_before": True,
                "available_now": False,
                "url": now.get("product_url"),
                "key": k,
            })

        if (old.get("available") is False) and now.get("available") is True:
            counts["restock"] += 1
            changes.append({
                "type": "RESTOCK",
                "title": now.get("title"),
                "variant_label": now.get("variant_label", ""),
                "category": now.get("category", ""),
                "old_price": _price_repr(old),
                "new_price": _price_repr(now),
                "available_before": False,
                "available_now": True,
                "url": now.get("product_url"),
                "key": k,
            })

    for k, old in prev.items():
        if k not in cur:
            counts["removed"] += 1
            changes.append({
                "type": "REMOVED",
                "title": old.get("title"),
                "variant_label": old.get("variant_label", ""),
                "category": old.get("category", ""),
                "old_price": _price_repr(old),
                "new_price": None,
                "available_before": old.get("available"),
                "available_now": None,
                "url": old.get("product_url"),
                "key": k,
            })

    order = {"NEW": 0, "PRICE": 1, "REMOVED": 2, "OOS": 3, "RESTOCK": 4}
    changes.sort(key=lambda x: (order.get(x["type"], 9), (x.get("title") or "")))

    return changes, counts
''',

  "<REPLACE_WITH_STORAGE_PY>": r'''
import json
import os
from glob import glob

def write_json(path, data):
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def _site_glob(snap_dir, site_id):
    return os.path.join(snap_dir, f"{site_id}__*.json")

def load_latest_snapshot(snap_dir, site_id):
    files = sorted(glob(_site_glob(snap_dir, site_id)))
    if not files:
        return None
    latest = files[-1]
    with open(latest, "r", encoding="utf-8") as f:
        return json.load(f)

def save_snapshot(snap_dir, site_id, snapshot):
    run_id = snapshot["run_id"]
    fn = os.path.join(snap_dir, f"{site_id}__{run_id}.json")
    write_json(fn, snapshot)

def prune_snapshots(snap_dir, keep_per_site=40):
    files = glob(os.path.join(snap_dir, "*.json"))
    by_site = {}
    for f in files:
        base = os.path.basename(f)
        if "__" not in base:
            continue
        site_id = base.split("__", 1)[0]
        by_site.setdefault(site_id, []).append(f)

    for site_id, fs in by_site.items():
        fs_sorted = sorted(fs)
        to_delete = fs_sorted[:-keep_per_site]
        for f in to_delete:
            try:
                os.remove(f)
            except Exception:
                pass
''',

  "<REPLACE_WITH_REPORT_PY>": r'''
def build_summary(site_results, run_id, time_utc):
    total = {"new": 0, "removed": 0, "price": 0, "restock": 0, "oos": 0}
    ok_sites = 0
    err_sites = 0

    for s in site_results:
        if s.get("status") == "ok":
            ok_sites += 1
            for k in total:
                total[k] += int(s.get("counts", {}).get(k, 0))
        else:
            err_sites += 1

    return {
        "run_id": run_id,
        "time_utc": time_utc,
        "sites_ok": ok_sites,
        "sites_error": err_sites,
        "totals": total,
    }
''',

  "<REPLACE_WITH_SHOPIFY_PY>": r'''
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
                        return {"products": products, "meta": meta}
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
                    return {"products": products, "meta": meta}
            page += 1

    return {"products": products, "meta": meta}

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
''',

  "<REPLACE_WITH_GENERIC_PY>": r'''
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
''',

  "<REPLACE_WITH_INDEX_HTML>": r'''
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Competitor Watch</title>
  <link rel="stylesheet" href="style.css"/>
</head>
<body>
  <header class="wrap">
    <h1>Competitor Watch</h1>
    <div id="meta" class="muted"></div>
  </header>

  <main class="wrap">
    <section class="card">
      <h2>Overview</h2>
      <div id="overview" class="grid"></div>
    </section>

    <section class="card">
      <h2>Sites</h2>
      <div id="sites"></div>
    </section>

    <section class="card">
      <h2>Errors</h2>
      <div id="errors" class="muted"></div>
    </section>
  </main>

  <script src="app.js"></script>
</body>
</html>
''',

  "<REPLACE_WITH_STYLE_CSS>": r'''
:root { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto; }
body { margin:0; background:#0b0f14; color:#e8eef6; }
.wrap { max-width: 1100px; margin: 0 auto; padding: 18px; }
h1 { margin: 10px 0 6px; font-size: 22px; }
h2 { margin: 0 0 12px; font-size: 16px; }
.card { background:#121826; border:1px solid #1e2a3a; border-radius:14px; padding:14px; margin: 14px 0; }
.muted { color:#9fb0c3; font-size: 13px; }
.grid { display:grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap:10px; }
.pill { background:#0f1521; border:1px solid #1e2a3a; border-radius:12px; padding:10px; }
.pill b { display:block; font-size: 16px; margin-bottom:4px; }
.site { border-top:1px solid #1e2a3a; padding:12px 0; }
.site:first-child { border-top:none; }
.site-head { display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; }
.tag { font-size:12px; padding:2px 8px; border-radius:999px; border:1px solid #26384e; color:#bcd0e6; }
.tag.ok { background:#0f2a1a; border-color:#1f5a35; }
.tag.err { background:#2a1212; border-color:#6a2a2a; }
ul { margin: 10px 0 0; padding-left: 18px; }
a { color:#8bd3ff; text-decoration:none; }
a:hover { text-decoration:underline; }
.change { margin: 8px 0; }
.change small { color:#9fb0c3; }
''',

  "<REPLACE_WITH_APP_JS>": r'''
async function jget(path) {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`Fetch failed: ${path}`);
  return r.json();
}

function fmtPrice(p) {
  if (!p) return "";
  const [minp, maxp] = p;
  if (minp == null && maxp == null) return "";
  if (minp === maxp) return `${minp}`;
  return `${minp}–${maxp}`;
}

function escapeHtml(s) {
  return (s || "")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;");
}

function renderOverview(sum) {
  const t = sum.totals || {};
  const items = [
    ["NEW", t.new || 0],
    ["PRICE", t.price || 0],
    ["REMOVED", t.removed || 0],
    ["OOS", t.oos || 0],
    ["RESTOCK", t.restock || 0],
  ];
  return items.map(([k,v]) => `
    <div class="pill"><b>${v}</b><div class="muted">${k}</div></div>
  `).join("");
}

function renderSite(site) {
  const badge = site.status === "ok"
    ? `<span class="tag ok">OK</span>`
    : `<span class="tag err">ERROR</span>`;

  const counts = site.counts || {};
  const headRight = site.status === "ok"
    ? `<span class="muted">NEW ${counts.new||0} · PRICE ${counts.price||0} · REMOVED ${counts.removed||0} · OOS ${counts.oos||0} · RESTOCK ${counts.restock||0}</span>`
    : `<span class="muted">${escapeHtml(site.error || "")}</span>`;

  const changes = (site.changes || []).slice(0, 200);
  const list = changes.length ? `
    <ul>
      ${changes.map(ch => {
        const type = ch.type;
        const title = escapeHtml(ch.title || "");
        const vlab = escapeHtml(ch.variant_label || "");
        const cat = escapeHtml(ch.category || "");
        const url = ch.url || "#";
        const oldp = fmtPrice(ch.old_price);
        const newp = fmtPrice(ch.new_price);
        const pricePart = (type === "PRICE") ? ` <small>(${oldp} → ${newp})</small>` : "";
        const meta = [cat, vlab].filter(Boolean).join(" · ");
        return `<li class="change"><b>${type}</b> <a href="${url}" target="_blank" rel="noreferrer">${title}</a>${pricePart}
          ${meta ? `<div><small>${meta}</small></div>` : ``}
        </li>`;
      }).join("")}
    </ul>
  ` : `<div class="muted">No changes detected.</div>`;

  return `
    <div class="site">
      <div class="site-head">
        <div>
          <b>${escapeHtml(site.name || site.site_id)}</b>
          <span class="muted"> · <a href="${site.base_url}" target="_blank" rel="noreferrer">${site.base_url}</a></span>
        </div>
        <div style="display:flex; gap:10px; align-items:center;">${badge}${headRight}</div>
      </div>
      ${list}
    </div>
  `;
}

async function main() {
  const meta = document.getElementById("meta");
  const overview = document.getElementById("overview");
  const sitesEl = document.getElementById("sites");
  const errorsEl = document.getElementById("errors");

  try {
    const [sum, sites, errors] = await Promise.all([
      jget("./data/summary.json"),
      jget("./data/sites.json"),
      jget("./data/errors.json"),
    ]);

    meta.textContent = `Last run (UTC): ${sum.time_utc} · Sites OK: ${sum.sites_ok} · Sites Error: ${sum.sites_error}`;
    overview.innerHTML = renderOverview(sum);
    sitesEl.innerHTML = (sites || []).map(renderSite).join("");

    if (errors && errors.length) {
      errorsEl.innerHTML = errors.map(e => `• ${escapeHtml(e.name)}: ${escapeHtml(e.error)}`).join("<br/>");
    } else {
      errorsEl.textContent = "No errors.";
    }
  } catch (e) {
    meta.textContent = "Failed to load dashboard data.";
    errorsEl.textContent = String(e);
  }
}

main();
''',

  "<REPLACE_WITH_WORKFLOW_YML>": r'''
name: competitor-watch

on:
  workflow_dispatch:
  schedule:
    - cron: "0 1 * * *"
    - cron: "0 7 * * *"
    - cron: "0 13 * * *"

permissions:
  contents: write

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run watcher
        run: |
          python src/run.py

      - name: Commit data
        run: |
          git config user.name "github-actions"
          git config user.email "github-actions@github.com"
          git add docs/data
          git commit -m "update: competitor watch data" || echo "No changes"
          git push
'''
}

def write_file(path, content):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(content))

def main():
    missing = [k for k,v in FILES.items() if "<REPLACE_WITH_" in v]
    if missing and not REPLACEMENTS:
        print("bootstrap.py created placeholders. Now paste real contents into REPLACEMENTS and re-run.")
    for path, content in FILES.items():
        for key, real in REPLACEMENTS.items():
            content = content.replace(key, real)
        write_file(path, content)
    print("Project scaffold generated.")

if __name__ == "__main__":
    main()