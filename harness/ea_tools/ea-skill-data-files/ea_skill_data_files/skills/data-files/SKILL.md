---
name: data-files
description: Structured data file processing - read, write, convert, and transform CSV, JSON, XML, YAML, TSV; validate and reshape structured data
aliases: [structured-data, csv-json]
when_to_use: ".csv .json .xml .yaml .yml .tsv .jsonl"
argument_hint: "[path to data file or task description]"
user_invocable: true
hidden: true
auto_activate: true
context: inline
---

## Structured Data File Processing

You are processing a structured data file: **{{args}}**

### When to Use
- Read CSV / JSON / XML / YAML / TSV / JSONL content
- Convert between structured formats (CSV <-> JSON <-> YAML)
- Validate structure (schema, required fields, types)
- Reshape data (filter, project, aggregate, join) for downstream use
- Move structured data into or out of a spreadsheet

### When NOT to Use
- **Visualize / chart data** -> once you have the data, use the `data-viz` skill; this skill is about reading/writing/converting
- **Excel .xlsx** -> use the `spreadsheet` tool / `xlsx` skill; CSV is plain text but .xlsx is binary
- **A single small config file** -> just `file_read` it; do not over-engineer with a parser
- **Log files** -> use the `debug` skill (`.log .err .out`)

### Processing Workflow
1. **Identify the format** -> check the extension and peek at the first lines with `file_read` to confirm structure (delimiter, nesting, header presence).
2. **Choose the operation:**
   - Read -> `file_read` for small files; `bash` + `jq`/`pandas`/`yq` for large or nested files
   - Convert -> parse with the right library, then `file_write` in the target format
   - Validate -> check required fields, types, and schema; report mismatches explicitly
   - Reshape -> use `bash` + pandas/jq to filter/project/aggregate, then write the result
3. **Size awareness** -> large CSV/JSON can flood context; read a sample (head + count) first, then decide.
4. **Preserve types** -> when converting CSV to JSON, numbers should stay numbers, not become strings; use a typed parser.
5. **Verify** -> after conversion, read a sample of the output to confirm structure and types survived.

### Tool Selection
- `file_read`: read small structured files directly (CSV, JSON, YAML, XML as text)
- `file_write`: write converted output in any format
- `bash` + `jq` (JSON), `yq` (YAML/XML), `pandas` (CSV/tabular), `xmltodot`/lxml (XML): heavy parsing, conversion, validation, reshaping
- `spreadsheet` tool: move data into/out of `.xlsx`
- `grep`: search within a data file for a value or key

### Best Practices
- Peek before parsing: read the first few lines to confirm delimiter, header, and nesting
- For large files, get the row/count first (`wc -l`, `jq length`) before reading content
- Preserve types across conversions - use typed parsers, not string concatenation
- Validate explicitly: missing fields, type mismatches, and duplicate keys are the common bugs
- When converting CSV to JSON, decide the record shape (list of objects vs keyed) deliberately

### Common Pitfalls
- **Reading a huge data file wholesale** -> floods context; sample first, count rows, then read what you need
- **Losing types on conversion** -> CSV to JSON via string ops turns numbers into strings; use a typed parser
- **Wrong delimiter** -> TSV vs CSV vs pipe-delimited; peek first
- **Ignoring nesting** -> JSONL (one object per line) is not the same as a JSON array; parse accordingly
- **Assuming a header row** -> some CSVs have no header; confirm before treating row 0 as keys

### Pairing with Other Tools
- `data-viz` - chart the data once read out
- `xlsx` / `spreadsheet` - move data into/out of Excel
- `bash` (jq/yq/pandas) - heavy parsing, conversion, reshaping
- `file_read` / `file_write` - read source, write output
- `grep` - search within a data file for a value
