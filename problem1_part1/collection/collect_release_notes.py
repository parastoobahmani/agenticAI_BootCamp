"""
collect_release_notes.py
1. GitHub Releases API
2. (optional) scrape the official release-notes pages
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO = "streamlit/streamlit"
OUT_DIR = Path(__file__).resolve().parents[1] / "data"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS = {"Accept": "application/vnd.github+json"}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"


def fetch_releases(max_releases: int = 40) -> list:
    releases = []
    page = 1
    while len(releases) < max_releases:
        r = requests.get(
            f"https://api.github.com/repos/{REPO}/releases",
            headers=HEADERS,
            params={"per_page": 30, "page": page},
            timeout=30,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        releases.extend(batch)
        page += 1
        time.sleep(0.5)
    return releases[:max_releases]


def main():
    raw = fetch_releases()
    notes = []
    for rel in raw:
        tag = rel["tag_name"].lstrip("v")
        notes.append({
            "id": f"release-{tag}",
            "source_type": "release_note",
            "title": rel.get("name") or f"Release {tag}",
            "content": rel.get("body") or "",
            "url_or_path": rel["html_url"],
            "version": tag,
            "date": rel.get("published_at"),
            "collected_at": datetime.now(timezone.utc).isoformat(),
        })

    out = OUT_DIR / "release_notes.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for n in notes:
            f.write(json.dumps(n, ensure_ascii=False) + "\n")
    print(f"Wrote {len(notes)} release notes → {out}")


if __name__ == "__main__":
    main()
