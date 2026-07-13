---
name: xlsx
description: Excel/spreadsheet (.xlsx/.xls) processing - read cells, write data, list sheets, handle formulas and tabular data
aliases: [excel, spreadsheet-doc]
when_to_use: ".xlsx .xls"
argument_hint: "[path to spreadsheet file or task description]"
user_invocable: true
hidden: true
auto_activate: true
context: inline
---

## Spreadsheet (.xlsx) Processing

You are processing a spreadsheet: **{{args}}**

### When to Use
- Read cell data from an Excel file (with or without formulas)
- Write data into a new or existing spreadsheet
- List the sheets in a multi-sheet workbook before reading
- Move tabular data between a spreadsheet and other formats (CSV, JSON)

### When NOT to Use
- **CSV / JSON / YAML files** -> use the `data-files` skill / `file_read`; do not invoke Excel tooling for plain structured text
- **Visualizing data** -> once you have the data, use the `data-viz` skill to chart it; spreadsheet handling is about reading/writing
- **Data analysis / statistics** -> read the data out, then use `data-viz` (descriptive stats, charts); the spreadsheet tool is not an analytics engine
- **A single small table** -> if it fits in text, just `file_read` the CSV

### Processing Workflow
1. **Survey the workbook** -> call `spreadsheet` with `action: list_sheets` to see sheet names before reading. Multi-sheet workbooks are common.
2. **Choose the operation:**
   - Read data -> `action: read` (specify the sheet if multi-sheet)
   - Write data -> `action: write` with clean row data
   - List sheets -> `action: list_sheets`
3. **Size awareness** -> large sheets can flood context; read a sample or the header + first rows first, then decide whether to read more.
4. **Verify writes** -> after `write`, re-read the target range to confirm values landed correctly.
5. **Cross-format** -> to move data to CSV/JSON, read it out then `file_write` in the target format.

### Tool Selection
- `spreadsheet` tool (registered): `action: read` / `write` / `list_sheets` - primary path for `.xlsx`/`.xls`
- `bash` + `openpyxl`/`pandas`: fallback for operations the tool lacks (formulas evaluation, named ranges, formatting, charts)
- `file_read`: usable for CSV, but not for binary `.xlsx`; use the `spreadsheet` tool for Excel
- `file_write` - save CSV/JSON exports

### Best Practices
- Always `list_sheets` first on an unknown workbook - assuming a single "Sheet1" breaks on multi-sheet files
- When writing, pass clean tabular data (list of rows); do not embed formulas as strings unless intentional
- For large sheets, read headers + a sample first; only read the full range if the task needs it
- Preserve the sheet name in your answer so the user knows which sheet you read

### Common Pitfalls
- **Reading the whole sheet blindly** -> can blow the context on a large workbook; sample first
- **Assuming a single sheet** -> multi-sheet workbooks are common; `list_sheets` first
- **Confusing displayed value with underlying value** -> a cell may show a formatted number but store a formula; read raw values when it matters
- **Overwriting a sheet without confirmation** -> `write` may replace; confirm the target sheet/range

### Pairing with Other Tools
- `data-viz` - chart the data once read out
- `data-files` - convert to/from CSV, JSON
- `file_write` - export to CSV/JSON
- `bash` (pandas/openpyxl) - heavy transformations, formula evaluation, formatting
- `grep` - search across exported CSV for a value
