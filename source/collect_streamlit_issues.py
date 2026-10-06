"""
collect_streamlit_issues.py
Fetches issues (not PRs) + comments from streamlit/streamlit.
Stores everything locally so evaluation never hits the live API again.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REPO = "streamlit/streamlit"
GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]  # strongly recommended
OUT_DIR = Path("data/raw")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Scope: session-state / widgets related labels (adjust as needed)
LABELS = [
    "feature:st.session_state",
    "area:widgets",
    "feature:st.selectbox",
    "feature:st.multiselect",
    "feature:st.slider",
    "type:bug",
]

# How many issues to keep (after filtering PRs)
MAX_ISSUES = 400
PER_PAGE = 100
SLEEP_BETWEEN_PAGES = 1.0  # be nice to the API
SLEEP_ON_RATE_LIMIT = 60

HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def gh_get(url: str, params: Optional[Dict] = None) -> Any:
    while True:
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        if r.status_code == 403 and "rate limit" in r.text.lower():
            print("Rate limited – sleeping …")
            time.sleep(SLEEP_ON_RATE_LIMIT)
            continue
        r.raise_for_status()
        return r.json()


def is_pull_request(item: Dict) -> bool:
    return "pull_request" in item


def fetch_issues() -> List[Dict]:
    """Paginate /repos/{repo}/issues and keep only real issues."""
    issues = []
    page = 1
    while len(issues) < MAX_ISSUES:
        params = {
            "state": "all",
            "per_page": PER_PAGE,
            "page": page,
            "sort": "updated",
            "direction": "desc",
        }
        # optional label filter – GitHub allows only one label per request,
        # so we fetch broadly and filter client-side if needed
        batch = gh_get(f"https://api.github.com/repos/{REPO}/issues", params)
        if not batch:
            break
        for item in batch:
            if is_pull_request(item):
                continue
            issues.append(item)
            if len(issues) >= MAX_ISSUES:
                break
        page += 1
        time.sleep(SLEEP_BETWEEN_PAGES)
        print(f"  fetched page {page - 1}, total issues so far: {len(issues)}")
    return issues[:MAX_ISSUES]


def fetch_comments(issue_number: int) -> List[Dict]:
    comments = []
    page = 1
    while True:
        batch = gh_get(
            f"https://api.github.com/repos/{REPO}/issues/{issue_number}/comments",
            params={"per_page": 100, "page": page},
        )
        if not batch:
            break
        comments.extend(batch)
        page += 1
        time.sleep(0.5)
    return comments


# ---------------------------------------------------------------------------
# Main collection
# ---------------------------------------------------------------------------
def main():
    meta = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "repo": REPO,
        "max_issues": MAX_ISSUES,
        "sampling": "most-recently-updated issues (PRs excluded), client-side label filter optional",
        "labels_considered": LABELS,
    }

    print("Fetching issues …")
    raw_issues = fetch_issues()
    print(f"Got {len(raw_issues)} issues")

    cleaned_issues = []
    all_comments = []

    for i, issue in enumerate(raw_issues, 1):
        number = issue["number"]
        print(f"[{i}/{len(raw_issues)}] issue #{number} – fetching comments …")
        comments = fetch_comments(number)

        # Keep only the fields required by the project brief
        cleaned = {
            "number": number,
            "html_url": issue["html_url"],
            "title": issue["title"],
            "body": issue.get("body") or "",
            "created_at": issue["created_at"],
            "updated_at": issue["updated_at"],
            "closed_at": issue.get("closed_at"),
            "state": issue["state"],
            "state_reason": issue.get("state_reason"),
            "labels": [lb["name"] for lb in issue.get("labels", [])],
            "comments_count": issue.get("comments", 0),
            "comments_url": issue.get("comments_url"),
        }
        cleaned_issues.append(cleaned)

        for c in comments:
            all_comments.append({
                "issue_number": number,
                "id": c["id"],
                "body": c.get("body") or "",
                "created_at": c["created_at"],
                "updated_at": c["updated_at"],
                "html_url": c["html_url"],
                "author_association": c.get("author_association"),
                "user_login": c.get("user", {}).get("login"),
            })

    # Write static files
    issues_path = OUT_DIR / "issues.jsonl"
    with issues_path.open("w", encoding="utf-8") as f:
        for item in cleaned_issues:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    comments_path = OUT_DIR / "comments.jsonl"
    with comments_path.open("w", encoding="utf-8") as f:
        for item in all_comments:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    meta["num_issues"] = len(cleaned_issues)
    meta["num_comments"] = len(all_comments)
    meta_path = OUT_DIR / "collection_meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print("\nDone.")
    print(f"  Issues  → {issues_path}  ({len(cleaned_issues)})")
    print(f"  Comments→ {comments_path} ({len(all_comments)})")
    print(f"  Meta    → {meta_path}")


if __name__ == "__main__":
    main()

