# Part 3 output

Default output: `response.json`, `user_response.txt`, `maintainer_summary.md`,
and `manifest.json`. Consumers should require `manifest.status == "complete"`,
check its `response_id` matches `response.json.id` and all file hashes match, and reject
`artifact_kind == "demonstration"` for real processing.

The tracked `example_*` files are an OFFLINE DEMONSTRATION generated
from `part1_2_output/example_part1_2_output.json`. They were not produced from a real teammate report:
the supplied file is only a schema. It shows the output format for integration.

Run `python -m part3` to process actual reports from `part1_2_output/`.
Run `python -m part3 --demo` to regenerate the explicitly labelled example.
Each run replaces the files directly in this directory; `case_id` remains inside the JSON.
If multiple input reports exist, select one explicitly with `python -m part3 part1_2_output/case123.json`.
Generated outputs are ignored by Git; use the bundled example to recreate them.
The active runtime files use names without the `example_` prefix and remain ignored. The
tracked example manifest describes those runtime names; its hashes match the corresponding
example files' contents.
