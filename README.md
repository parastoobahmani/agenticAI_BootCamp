Step,Command / Action,Output
1,export GITHUB_TOKEN=…,– (the only input)
2,python collect_streamlit_issues.py,data/raw/issues.jsonl + comments.jsonl --> (as an intermediate result)
3,python collect_streamlit_docs.py,data/raw/documentation.jsonl --> (as an intermediate result)
4,python collect_release_notes.py,data/raw/release_notes.jsonl --> (as an intermediate result)
5,Record counts & timestamps in the meta files,reproducibility --> (as an intermediate result)
6,Run evidence_synthesis_streamlit.py on any new report,evidence_synthesis_result.json (the output for the next step)