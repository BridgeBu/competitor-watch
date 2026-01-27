
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

