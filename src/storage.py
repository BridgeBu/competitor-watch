
import json
import os
from glob import glob
from datetime import datetime, timezone, timedelta

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

def load_snapshot_days_ago(snap_dir, site_id, days=3):
    """Return the latest snapshot whose time_utc is <= (now - days).
    If no such snapshot exists, fall back to the latest snapshot.
    """
    files = sorted(glob(_site_glob(snap_dir, site_id)))
    if not files:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(days=float(days))

    best = None
    best_t = None

    for fpath in files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                snap = json.load(f)
            t_raw = snap.get("time_utc")
            if not t_raw:
                continue
            t = datetime.fromisoformat(t_raw)
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)

            if t <= cutoff and (best_t is None or t > best_t):
                best = snap
                best_t = t
        except Exception:
            continue

    if best is not None:
        return best
    
    # Fallback (history < days): use the earliest snapshot as baseline
    oldest = None
    oldest_t = None
    
    for fpath in files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                snap = json.load(f)
            t_raw = snap.get("time_utc")
            if not t_raw:
                continue
            t = datetime.fromisoformat(t_raw)
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
    
            if oldest_t is None or t < oldest_t:
                oldest = snap
                oldest_t = t
        except Exception:
            continue
    
    return oldest or load_latest_snapshot(snap_dir, site_id)


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

