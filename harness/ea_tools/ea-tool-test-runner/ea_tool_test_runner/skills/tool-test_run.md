---
name: tool-test_run
description: "Run the project's test suite and return a structured JSON report. Auto-detects pytest, vitest, jest, and cargo test from project files. Use this instead of invoking the test runner directly via bash -- it parses results into per-test status (passed/failed/skipped/error), duration, file location, and a truncated failure message, so you can decide which tests to fix and where. Use the 'filter' argument to scope to a single test (pytest -k, jest/vitest -t, cargo test name). TIP: After a code change, run with a narrow 'filter' on the affected tests first, then run the full suite. AVOID: Running the full suite repeatedly without a filter when iterating on one test -- use the filter to stay fast."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# test_run

Run the project's test suite and return a structured JSON report. Auto-detects pytest, vitest, jest, and cargo test from project files. Use this instead of invoking the test runner directly via bash -- it parses results into per-test status (passed/failed/skipped/error), duration, file location, and a truncated failure message, so you can decide which tests to fix and where. Use the 'filter' argument to scope to a single test (pytest -k, jest/vitest -t, cargo test name). TIP: After a code change, run with a narrow 'filter' on the affected tests first, then run the full suite. AVOID: Running the full suite repeatedly without a filter when iterating on one test -- use the filter to stay fast.
