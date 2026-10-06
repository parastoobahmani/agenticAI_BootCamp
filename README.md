Step,Command / Action,Output
1,export GITHUB_TOKEN=…,–
2,python collect_streamlit_issues.py,data/raw/issues.jsonl + comments.jsonl
3,python collect_streamlit_docs.py,data/raw/documentation.jsonl
4,python collect_release_notes.py,data/raw/release_notes.jsonl
5,Record counts & timestamps in the meta files,reproducibility
6,Run evidence_synthesis_streamlit.py on any new report,evidence_synthesis_result.json