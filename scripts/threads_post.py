#!/usr/bin/env python3
"""Post scheduled Threads posts from content/posts.json via the official Threads API.

Standard library only (no pip install needed).

Usage:
  python3 scripts/threads_post.py --check     # validate posts.json, print schedule
  python3 scripts/threads_post.py --dry-run   # show what would be posted now
  python3 scripts/threads_post.py             # actually post what is due

Env:
  THREADS_ACCESS_TOKEN  (required to post)
  THREADS_USER_ID       (optional, default "me")
  MAX_LATE_HOURS        (optional, default 6) skip posts that are older than this
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS_FILE = ROOT / "content" / "posts.json"
POSTED_FILE = ROOT / "content" / "posted.json"
API = "https://graph.threads.net/v1.0"
MAX_CHARS = 500
PLACEHOLDER = re.compile(r"\[[^\]]*\]")
MYT = timezone(timedelta(hours=8))


def load_json(path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def parse_time(value):
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=MYT)  # default: Malaysia time
    return dt


def problems(post):
    """Return a list of reasons this post cannot be published yet."""
    out = []
    text = post.get("text", "")
    if not text.strip():
        out.append("text kosong")
    if len(text) > MAX_CHARS:
        out.append(f"text {len(text)} aksara (had {MAX_CHARS})")
    if PLACEHOLDER.search(text):
        out.append("masih ada [placeholder] yang belum diisi: "
                   + ", ".join(sorted(set(PLACEHOLDER.findall(text)))))
    if post.get("require_media") and not (post.get("video_url") or post.get("image_url")):
        out.append("perlu video/gambar tapi video_url/image_url kosong")
    if post.get("video_url") and post.get("image_url"):
        out.append("pilih satu sahaja: video_url atau image_url")
    for key in ("video_url", "image_url"):
        if post.get(key):
            try:
                direct_media_url(post[key])
            except ValueError as e:
                out.append(f"{key}: {e}")
    try:
        parse_time(post["scheduled_at"])
    except (KeyError, ValueError):
        out.append("scheduled_at tak sah (contoh: 2026-11-09T21:00:00+08:00)")
    return out


def api_call(method, path, params):
    url = f"{API}/{path}"
    data = None
    if method == "GET":
        url += "?" + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"Threads API {e.code}: {body}") from None


DRIVE_ID = re.compile(r"drive\.google\.com/(?:file/d/|open\?id=|uc\?(?:[^#]*&)?id=)([\w-]+)")


def direct_media_url(url):
    """Turn a Google Drive share link into a direct download link.

    Drive's normal share link opens a web page, but the Threads API needs a
    link straight to the .mp4/.jpg file. Folder links cannot be used.
    """
    if "drive.google.com/drive/folders" in url:
        raise ValueError("ini link FOLDER Drive; perlu link FAIL video (Share → Copy link pada video itu)")
    m = DRIVE_ID.search(url)
    if m:
        return f"https://drive.usercontent.google.com/download?id={m.group(1)}&export=download&confirm=t"
    return url


def check_media(url, kind):
    """Make sure the link really serves a public video/image file."""
    req = urllib.request.Request(url, headers={"Range": "bytes=0-1023", "User-Agent": "threads-autopost"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            ctype = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Link media tak boleh dibuka (HTTP {e.code}). Pastikan share 'Anyone with the link'.") from None
    if not (ctype.startswith(kind + "/") or ctype.startswith("application/octet-stream")):
        raise RuntimeError(f"Link bukan fail {kind} terus (Content-Type: {ctype or '?'}). "
                           "Pastikan fail Drive di-share 'Anyone with the link'.")


def publish(post, token, user_id):
    params = {"text": post["text"], "access_token": token}
    if post.get("video_url"):
        url = direct_media_url(post["video_url"])
        check_media(url, "video")
        params.update(media_type="VIDEO", video_url=url)
    elif post.get("image_url"):
        url = direct_media_url(post["image_url"])
        check_media(url, "image")
        params.update(media_type="IMAGE", image_url=url)
    else:
        params["media_type"] = "TEXT"
    if post.get("topic_tag"):
        params["topic_tag"] = post["topic_tag"]

    try:
        container = api_call("POST", f"{user_id}/threads", params)
    except RuntimeError as e:
        if "topic_tag" not in params:
            raise
        print(f"  ! Gagal dengan topic_tag, cuba semula tanpa topic: {e}")
        params.pop("topic_tag")
        container = api_call("POST", f"{user_id}/threads", params)
    cid = container["id"]

    # Media needs processing before it can be published.
    if params["media_type"] != "TEXT":
        for _ in range(30):
            st = api_call("GET", cid, {"fields": "status,error_message", "access_token": token})
            if st.get("status") == "FINISHED":
                break
            if st.get("status") in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"Media gagal diproses: {st}")
            time.sleep(10)
        else:
            raise RuntimeError("Media ambil masa terlalu lama untuk diproses")
    else:
        time.sleep(3)

    result = api_call("POST", f"{user_id}/threads_publish",
                      {"creation_id": cid, "access_token": token})
    media_id = result["id"]
    link = None
    try:
        link = api_call("GET", media_id, {"fields": "permalink", "access_token": token}).get("permalink")
    except RuntimeError:
        pass
    return media_id, link


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="validate all posts and exit")
    ap.add_argument("--dry-run", action="store_true", help="do not post, just show")
    args = ap.parse_args()

    posts = load_json(POSTS_FILE, [])
    posted = load_json(POSTED_FILE, {})
    ids = [p.get("id") for p in posts]
    if len(ids) != len(set(ids)) or None in ids:
        sys.exit("ERROR: setiap post perlu 'id' yang unik")

    now = datetime.now(timezone.utc)

    if args.check:
        bad = 0
        for p in sorted(posts, key=lambda p: p.get("scheduled_at", "")):
            issues = problems(p)
            state = "SUDAH POST" if p["id"] in posted else ("OK" if not issues else "BELUM SEDIA")
            print(f"[{state:11}] {p['id']:<4} {p.get('scheduled_at', '?')}  {p.get('text', '')[:40]!r}")
            for i in issues:
                print(f"              - {i}")
            if not issues and p["id"] not in posted:
                for key, kind in (("video_url", "video"), ("image_url", "image")):
                    if p.get(key):
                        try:
                            check_media(direct_media_url(p[key]), kind)
                            print(f"              - {key}: link OK ✓")
                        except Exception as e:
                            print(f"              - {key}: MASALAH: {e}")
                            issues.append(str(e))
            if issues and p["id"] not in posted:
                bad += 1
        print(f"\n{len(posts)} post, {len(posted)} sudah dipost, {bad} belum sedia.")
        return  # not-ready posts are warnings, not failures

    max_late = timedelta(hours=float(os.environ.get("MAX_LATE_HOURS", "6")))
    due = [p for p in posts
           if p["id"] not in posted and not problems(p)
           and now - max_late <= parse_time(p["scheduled_at"]) <= now]
    for p in posts:
        if p["id"] in posted:
            continue
        t = parse_time(p["scheduled_at"]) if "scheduled_at" in p else None
        if t and t <= now and problems(p):
            print(f"SKIP {p['id']}: " + "; ".join(problems(p)))
        elif t and t < now - max_late:
            print(f"TERLEPAS {p['id']}: dijadualkan {p['scheduled_at']}, lebih {max_late} lalu. Tukar tarikh jika nak post.")

    if not due:
        print("Tiada post yang perlu dihantar sekarang.")
        return

    token = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
    user_id = os.environ.get("THREADS_USER_ID", "").strip() or "me"
    if not token and not args.dry_run:
        sys.exit("ERROR: THREADS_ACCESS_TOKEN belum diset dalam GitHub Secrets")

    failed = False
    for p in sorted(due, key=lambda p: p["scheduled_at"]):
        print(f"POST {p['id']} ({p['scheduled_at']}): {p['text'][:60]!r}")
        if args.dry_run:
            continue
        try:
            media_id, link = publish(p, token, user_id)
        except Exception as e:  # keep going with other posts
            print(f"  X GAGAL: {e}")
            failed = True
            continue
        posted[p["id"]] = {"media_id": media_id, "permalink": link,
                           "posted_at": datetime.now(MYT).isoformat(timespec="seconds")}
        save_json(POSTED_FILE, posted)  # save after each post to avoid double posting
        print(f"  ✓ Berjaya: {link or media_id}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
