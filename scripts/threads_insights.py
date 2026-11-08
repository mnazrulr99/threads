#!/usr/bin/env python3
"""Collect Threads insights (per post + account) into content/insights/.

Needs a token with the threads_manage_insights permission.
Standard library only.

Writes:
  content/insights/latest.json   full snapshot (overwritten each run)
  content/insights/history.csv   one row per post per day (appended)
  content/insights/RINGKASAN.md  readable table, newest posts first
"""
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from threads_post import api_call, load_json, POSTED_FILE, POSTS_FILE, MYT  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "content" / "insights"
POST_METRICS = ["views", "likes", "replies", "reposts", "quotes", "shares"]
ACCOUNT_METRICS = ["views", "likes", "replies", "reposts", "quotes", "followers_count"]
MAX_POSTS = 100


def metric_values(resp):
    out = {}
    for m in resp.get("data", []):
        if "total_value" in m:
            out[m["name"]] = m["total_value"].get("value", 0)
        else:
            out[m["name"]] = sum(v.get("value", 0) for v in m.get("values", []))
    return out


def fetch_metrics(path, metrics, token, extra=None):
    """Ask for all metrics at once; if that fails, ask one by one."""
    params = {"metric": ",".join(metrics), "access_token": token, **(extra or {})}
    try:
        return metric_values(api_call("GET", path, params))
    except RuntimeError:
        out = {}
        for m in metrics:
            try:
                out.update(metric_values(api_call("GET", path, {**params, "metric": m})))
            except RuntimeError as e:
                print(f"  ! {path} metric {m} gagal: {str(e)[:150]}")
        return out


def list_posts(user_id, token):
    posts, params = [], {"fields": "id,media_type,text,timestamp,permalink", "limit": 50, "access_token": token}
    path = f"{user_id}/threads"
    while len(posts) < MAX_POSTS:
        resp = api_call("GET", path, params)
        posts.extend(resp.get("data", []))
        after = resp.get("paging", {}).get("cursors", {}).get("after")
        if not after or not resp.get("paging", {}).get("next"):
            break
        params = {**params, "after": after}
    return posts[:MAX_POSTS]


def main():
    token = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
    if not token:
        sys.exit("ERROR: THREADS_ACCESS_TOKEN belum diset")
    user_id = os.environ.get("THREADS_USER_ID", "").strip() or "me"

    # Link API posts back to our schedule (id, topic, scheduled time).
    posted = load_json(POSTED_FILE, {})
    plan = {p["id"]: p for p in load_json(POSTS_FILE, [])}
    by_media = {v["media_id"]: k for k, v in posted.items()}

    now = datetime.now(MYT)
    try:
        threads = list_posts(user_id, token)
    except RuntimeError as e:
        sys.exit(f"ERROR: gagal senaraikan post: {e}")

    rows = []
    for t in threads:
        m = fetch_metrics(f"{t['id']}/insights", POST_METRICS, token)
        pid = by_media.get(t["id"])
        p = plan.get(pid, {})
        ts = datetime.strptime(t["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(MYT)
        rows.append({
            "media_id": t["id"],
            "jadual_id": pid or "",
            "posted_at": ts.isoformat(timespec="minutes"),
            "jenis_media": t.get("media_type", ""),
            "topic": p.get("topic_tag", ""),
            "auto": bool(pid),
            "text": (t.get("text") or "").split("\n")[0][:80],
            "permalink": t.get("permalink", ""),
            **{k: m.get(k) for k in POST_METRICS},
        })

    # Account totals for the last 30 days (API allows since/until).
    since = int((now - timedelta(days=30)).timestamp())
    account = fetch_metrics(f"{user_id}/threads_insights", ACCOUNT_METRICS, token,
                            {"since": since, "until": int(now.timestamp())})

    OUT.mkdir(parents=True, exist_ok=True)
    snapshot = {"diambil_pada": now.isoformat(timespec="minutes"),
                "akaun_30_hari": account, "posts": rows}
    with (OUT / "latest.json").open("w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
        f.write("\n")

    hist = OUT / "history.csv"
    fields = ["tarikh", "media_id", "jadual_id", "posted_at", *POST_METRICS]
    new_file = not hist.exists()
    with hist.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow({"tarikh": now.date().isoformat(), **{k: r[k] for k in fields if k != "tarikh"}})

    def n(v):
        return "–" if v is None else str(v)

    lines = [
        "# Ringkasan Insights Threads",
        "",
        f"Dikemas kini: **{now:%d %b %Y, %I:%M %p}** (waktu Malaysia)",
        "",
        "## Akaun (30 hari lepas)",
        "",
        "| Followers | Views | Likes | Replies | Reposts | Quotes |",
        "|---|---|---|---|---|---|",
        "| " + " | ".join(n(account.get(k)) for k in
                          ["followers_count", "views", "likes", "replies", "reposts", "quotes"]) + " |",
        "",
        "## Setiap post (terbaru di atas)",
        "",
        "| Tarikh | Post | Auto? | 👁️ | ❤️ | 💬 | 🔁 | ✈️ |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        label = r["text"].replace("|", "/") or "(tiada teks)"
        lines.append(f"| {r['posted_at'][:16].replace('T', ' ')} | [{label}]({r['permalink']}) "
                     f"| {r['jadual_id'] or 'manual'} | {n(r['views'])} | {n(r['likes'])} "
                     f"| {n(r['replies'])} | {n(r['reposts'])} | {n(r['shares'])} |")
    (OUT / "RINGKASAN.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    missing = all(r["views"] is None and r["likes"] is None for r in rows) if rows else True
    print(f"✓ {len(rows)} post diambil. Followers: {n(account.get('followers_count'))}")
    if rows and missing:
        sys.exit("ERROR: tiada metrik diterima. Pastikan token baru ada permission threads_manage_insights.")


if __name__ == "__main__":
    main()
