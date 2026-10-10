from corpus import Snapshot, excluded_issue_ids

CUTOFF = "2026-05-01T00:00:00Z"


def _snapshot():
    return Snapshot(
        issues=[
            {"number": 1, "title": "Old bug", "body": "body", "created_at": "2026-01-01T00:00:00Z",
             "state": "closed", "labels": ["type:bug"], "html_url": "u1"},
            {"number": 2, "title": "Future bug", "body": "body", "created_at": "2026-06-01T00:00:00Z", "html_url": "u2"},
            {"number": 3, "title": "Eval case", "body": "body", "created_at": "2026-01-01T00:00:00Z", "html_url": "u3"},
        ],
        comments_by_issue={
            "1": [
                {"body": "before cutoff", "created_at": "2026-02-01T00:00:00Z", "author_association": "NONE"},
                {"body": "after cutoff: fixed in 1.99", "created_at": "2026-07-01T00:00:00Z", "author_association": "MEMBER"},
            ]
        },
        docs=[{"id": "doc-a", "title": "Doc", "content": "text", "url_or_path": "d", "commit": "abc"}],
        releases=[
            {"id": "release-1.0", "title": "1.0", "content": "c", "date": "2026-03-01T00:00:00Z", "version": "1.0"},
            {"id": "release-2.0", "title": "2.0", "content": "c", "date": "2026-08-01T00:00:00Z", "version": "2.0"},
        ],
        docs_commit="abc",
    )


def test_corpus_respects_cutoff_and_excludes_evaluation_cases():
    documents = {document.id: document for document in _snapshot().corpus_for(CUTOFF, {"issue-3"})}

    assert set(documents) == {"issue-1", "doc-a", "release-1.0"}
    issue = documents["issue-1"].content
    assert "before cutoff" in issue
    assert "after cutoff" not in issue
    assert "closed" not in issue and "type:bug" not in issue


def test_documentation_comes_from_the_pinned_snapshot():
    snapshot = _snapshot()
    [doc] = [document for document in snapshot.corpus_for(CUTOFF, set()) if document.source_type == "documentation"]
    assert doc.version == "abc"
    assert "abc" in snapshot.policy()["documentation"]


def test_excluded_ids_cover_both_splits_and_recurring_families():
    split = {"dev_case_ids": ["issue-1"], "test_case_ids": ["issue-2"]}
    cases = [{"case_id": "issue-1", "recurring_issue_numbers": [7]}]
    assert excluded_issue_ids(split, cases) == {"issue-1", "issue-2", "issue-7"}
