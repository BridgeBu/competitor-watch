
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

