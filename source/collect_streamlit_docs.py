"""
collect_streamlit_docs.py
Clones / updates the docs repo and extracts clean Markdown pages.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

DOCS_REPO = "https://github.com/streamlit/docs.git"
DOCS_DIR = Path("data/raw/docs_repo")
OUT_DIR = Path("data/raw")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Focus on the most relevant sections for session-state / widgets
INCLUDE_PREFIXES = [
    "content/develop/api-reference",
    "content/develop/concepts",
    "content/get-started",
    "content/knowledge-base",
]


def ensure_repo():
    if DOCS_DIR.exists():
        subprocess.run(["git", "-C", str(DOCS_DIR), "pull"], check=True)
    else:
        subprocess.run(["git", "clone", "--depth", "1", DOCS_REPO, str(DOCS_DIR)], check=True)


def extract_frontmatter_and_body(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip('"').strip("'")
    return fm, parts[2].strip()


def main():
    ensure_repo()
    commit = subprocess.check_output(
        ["git", "-C", str(DOCS_DIR), "rev-parse", "HEAD"], text=True
    ).strip()

    docs = []
    for md in DOCS_DIR.rglob("*.md"):
        rel = md.relative_to(DOCS_DIR).as_posix()
        if not any(rel.startswith(p) for p in INCLUDE_PREFIXES):
            continue
        raw = md.read_text(encoding="utf-8", errors="replace")
        fm, body = extract_frontmatter_and_body(raw)
        title = fm.get("title") or md.stem.replace("-", " ").title()
        slug = fm.get("slug") or "/" + rel.replace(".md", "")
        docs.append({
            "id": f"doc-{rel.replace('/', '-')}",
            "source_type": "documentation",
            "title": title,
            "content": body,
            "url_or_path": f"https://docs.streamlit.io{slug}",
            "version": None,  # docs are continuously updated
            "commit": commit,
            "section": rel,
            "collected_at": datetime.now(timezone.utc).isoformat(),
        })

    out = OUT_DIR / "documentation.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    meta = {
        "num_docs": len(docs),
        "docs_commit": commit,
        "include_prefixes": INCLUDE_PREFIXES,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
    (OUT_DIR / "docs_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"Wrote {len(docs)} documentation pages → {out}")


if __name__ == "__main__":
    main()
