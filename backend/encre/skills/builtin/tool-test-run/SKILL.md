---
name: tool-test-run
description: Test runner skill. workspace/framework/filter/max_duration, run project tests instead of bare bash
hidden: true
context: inline
---

## When to Use
- Run the project's test suite after changes
- Run a specific test file/case via filter
- Verify a fix didn't regress

## When NOT to Use
- **Run bare `pytest`/`npm test` in bash** -> use this tool; it integrates with the project's test runner config
- **Lint/format** -> `lint_format`
- **Build** -> `bash` (no dedicated build tool)

## Key Parameters
- `workspace`: project root, defaults to current workspace
- `framework`: test framework hint (pytest/unittest/jest/vitest/cargo), auto-detected if omitted
- `filter`: test selector, e.g. a file path, `TestClass::test_method`, or a name pattern
- `max_duration`: cap runtime in seconds; long suites should set this

## Best Practices
- After an edit, run only the related tests via `filter` first (fast feedback), then the full suite
- Set `max_duration` for large suites to avoid hanging
- If a test fails, read the failure, trace it to the change, fix, then re-run that test

## Common Pitfalls / Anti-patterns
- **Running the full suite for every change**: slow; filter to related tests first
- **No timeout on large suites**: can hang the turn
- **Using bash for tests**: use this tool for proper framework detection and result parsing
- **Ignoring pre-existing failures**: distinguish new failures from pre-existing ones before concluding a regression

## Pairing with Other Tools
- `lint_format`: check style/typing alongside tests
- `file_edit`: fix a failing test or the code under test, then re-run
- `bash`: for build steps that tests depend on
