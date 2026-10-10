# Part 3 output

Default output: `cases/<case_id>/<response_id>/response.json`,
`proposed_user_reply.txt`, `maintainer_summary.md`, and `manifest.json`.
Consumers should require `manifest.status == "complete"`,
check its `response_id` matches `response.json.id` and all file hashes match, and reject
`artifact_kind == "demonstration"` for real processing.

The tracked `example_*` files are an OFFLINE DEMONSTRATION generated
from `problem1_part2_output/example_problem1_part2_output.json`. They were not produced from a real teammate report:
the supplied file is only a schema. It shows the output format for integration.

Run `python -m problem1_part3` to process all actual reports from `problem1_part2_output/`.
Run `python -m problem1_part3 --demo` to regenerate the explicitly labelled example.
Each response directory is immutable. Reprocessing changed case data creates a new
content-derived `response_id` revision without deleting earlier responses. Process one
report explicitly with `python -m problem1_part3 problem1_part2_output/case123.json`.
Generated `cases/` outputs are ignored by Git; the tracked `example_*` files document
one complete demonstration artifact, and their contents match its manifest hashes.
