"""Search and download free stock footage from Pexels and Pixabay.

Keys come from environment variables (or .env): PEXELS_API_KEY, PIXABAY_API_KEY.
Every download is recorded in the short's assets.lock.json with its source
page, author and licence name, so credits and provenance are never guessed.

Check each provider's current API docs and licence terms before relying on
this; rate limits and terms can change.
  Pexels:  https://www.pexels.com/api/documentation/  (licence: https://www.pexels.com/license/)
  Pixabay: https://pixabay.com/api/docs/              (licence: https://pixabay.com/service/license-summary/)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

from .config import HEIGHT, LIBRARY_DIR, ROOT, load_env
from .spec import Scene, Spec

TIMEOUT = 30
FOOTAGE_DIR = LIBRARY_DIR / "footage"


class StockError(RuntimeError):
    pass


def _key(name: str) -> str:
    load_env()
    key = os.environ.get(name, "").strip()
    if not key:
        raise StockError(f"{name} is not set. Add it to .env (see .env.example).")
    return key


def _best_file(files: list[dict]) -> dict | None:
    """Prefer portrait files at least 1920px tall, the smallest such; else the tallest."""
    usable = [f for f in files if f.get("link") and f.get("width") and f.get("height")]
    if not usable:
        return None
    portrait = [f for f in usable if f["height"] > f["width"]]
    pool = portrait or usable
    big = [f for f in pool if max(f["width"], f["height"]) >= HEIGHT]
    if big:
        return min(big, key=lambda f: f["width"] * f["height"])
    return max(pool, key=lambda f: f["width"] * f["height"])


def search_pexels(query: str, per_page: int = 15) -> list[dict]:
    r = requests.get("https://api.pexels.com/videos/search",
                     params={"query": query, "orientation": "portrait", "per_page": per_page},
                     headers={"Authorization": _key("PEXELS_API_KEY")}, timeout=TIMEOUT)
    r.raise_for_status()
    return normalize_pexels(r.json())


def normalize_pexels(data: dict) -> list[dict]:
    out = []
    for v in data.get("videos", []):
        files = [{"link": f.get("link"), "width": f.get("width"), "height": f.get("height")}
                 for f in v.get("video_files", []) if f.get("file_type", "video/mp4") == "video/mp4"]
        best = _best_file(files)
        if best:
            out.append({"provider": "pexels", "id": str(v["id"]), "page_url": v.get("url"),
                        "author": (v.get("user") or {}).get("name"),
                        "author_url": (v.get("user") or {}).get("url"),
                        "duration": v.get("duration"), "download": best["link"],
                        "width": best["width"], "height": best["height"],
                        "license": "Pexels License"})
    return out


def search_pixabay(query: str, per_page: int = 20) -> list[dict]:
    r = requests.get("https://pixabay.com/api/videos/",
                     params={"key": _key("PIXABAY_API_KEY"), "q": query, "per_page": per_page,
                             "safesearch": "true"}, timeout=TIMEOUT)
    r.raise_for_status()
    return normalize_pixabay(r.json())


def normalize_pixabay(data: dict) -> list[dict]:
    out = []
    for h in data.get("hits", []):
        files = [{"link": f.get("url"), "width": f.get("width"), "height": f.get("height")}
                 for f in (h.get("videos") or {}).values()]
        best = _best_file(files)
        if best:
            out.append({"provider": "pixabay", "id": str(h["id"]), "page_url": h.get("pageURL"),
                        "author": h.get("user"),
                        "author_url": f"https://pixabay.com/users/{h.get('user')}-{h.get('user_id')}/",
                        "duration": h.get("duration"), "download": best["link"],
                        "width": best["width"], "height": best["height"],
                        "license": "Pixabay Content License"})
    # portrait results first, keeping the provider's relevance order otherwise
    return sorted(out, key=lambda c: c["height"] <= c["width"])


def choose(candidates: list[dict], pick: int, min_duration: float, exclude: set[str]) -> dict | None:
    fresh = [c for c in candidates if f"{c['provider']}-{c['id']}" not in exclude]
    long_enough = [c for c in fresh if (c.get("duration") or 0) >= min_duration]
    pool = long_enough or fresh
    return pool[pick] if pick < len(pool) else (pool[-1] if pool else None)


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    with requests.get(url, stream=True, timeout=TIMEOUT) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    tmp.replace(dest)


def fetch(spec: Spec, refresh: bool = False) -> list[str]:
    """Download footage for every scene that has a `query` and no `file`."""
    lock = spec.load_lock()
    scenes_lock: dict = lock.setdefault("scenes", {})
    used = {f"{e['provider']}-{e['id']}" for e in scenes_lock.values()}
    log: list[str] = []
    for scene in spec.scenes:
        if scene.footage.file or not scene.footage.query:
            continue
        key = str(scene.index)
        entry = scenes_lock.get(key)
        if entry and not refresh and entry.get("query") == scene.footage.query \
                and entry.get("pick") == scene.footage.pick and (ROOT / entry["file"]).exists():
            log.append(f"scene {scene.index}: already have {entry['file']}")
            continue
        if entry:
            used.discard(f"{entry['provider']}-{entry['id']}")
        log.append(_fetch_scene(scene, scenes_lock, used))
    spec.lock_path.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return log


def _fetch_scene(scene: Scene, scenes_lock: dict, used: set[str]) -> str:
    f = scene.footage
    search = search_pexels if f.provider == "pexels" else search_pixabay
    min_dur = f.start + scene.duration
    choice = choose(search(f.query), f.pick, min_dur, used)
    if not choice:
        raise StockError(f"scene {scene.index}: no {f.provider} results for {f.query!r}")
    dest = FOOTAGE_DIR / f"{choice['provider']}-{choice['id']}-{choice['height']}p.mp4"
    if not dest.exists():
        _download(choice["download"], dest)
    used.add(f"{choice['provider']}-{choice['id']}")
    scenes_lock[str(scene.index)] = {
        "query": f.query, "pick": f.pick, "file": str(dest.relative_to(ROOT)),
        **{k: choice[k] for k in ("provider", "id", "page_url", "author", "author_url",
                                  "license", "width", "height", "duration")},
        "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return f"scene {scene.index}: {choice['provider']} #{choice['id']} by {choice['author']} -> {dest.name}"


def credits(spec: Spec) -> str:
    """Plain-text credits for the video description / records."""
    lines = []
    seen = set()
    for e in spec.load_lock().get("scenes", {}).values():
        k = (e["provider"], e["id"])
        if k in seen:
            continue
        seen.add(k)
        lines.append(f"Footage: {e.get('author')} on {e['provider'].capitalize()} - {e.get('page_url')}")
    lines += spec.credits
    return "\n".join(lines)
