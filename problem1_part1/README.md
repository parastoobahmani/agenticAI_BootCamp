# Problem 1 Part 1

This folder owns evidence collection and synthesis:

- `collection/`: GitHub issue, documentation and release-note collectors.
- `data/`: the reproducible local source snapshot and synthesis artifact.
- `evidence_synthesis/`: retrieval and evidence-synthesis implementation.

Run commands from the repository root:

```bash
python -m problem1_part1.collection.collect_streamlit_issues
python -m problem1_part1.collection.collect_streamlit_docs
python -m problem1_part1.collection.collect_release_notes
python -m problem1_part1.evidence_synthesis.evidence_synthesis_streamlit
```

The collectors perform network access. Evidence synthesis reads the stored
snapshot and runs offline.
