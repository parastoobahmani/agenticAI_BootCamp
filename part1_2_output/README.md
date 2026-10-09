# Part 2 output — input to Part 3

`next_step_report.schema.json` is the supplied format definition, copied unchanged.
`example_part1_2_output.json` is a fictional, populated example for integration and is
ignored by normal runs. It is used only when `python -m part1_3 --demo` is requested.
It is NOT a populated case report. The default Part 3 command skips schema files.

Part 2 should write its actual serialized JSON report here, for example `case-123.json`.
The report must match the existing schema. No Part 3 Python class is required.
Use a temporary filename and rename it to `.json` when writing is complete.

From the project root, `python -m part1_3` processes the populated reports here.
There is currently no actual teammate-generated report in this folder.
