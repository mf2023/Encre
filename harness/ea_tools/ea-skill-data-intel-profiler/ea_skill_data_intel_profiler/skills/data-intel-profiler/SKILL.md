---
name: data-intel-profiler
version: "1.0.0"
description: >
  Enterprise-grade data insight analysis for structured data (CSV/Excel/JSON).
  Covers intelligent statistical profiling, data cleaning & preprocessing,
  NL2SQL translation, automated report generation with interpretation, and
  business metric anomaly detection with root-cause attribution. Designed for
  robust, exception-safe deployment in production analytics pipelines.
tags:
  - data-analysis
  - csv
  - excel
  - nl2sql
  - anomaly-detection
  - business-intelligence
  - data-cleaning
  - reporting
dependencies:
  python: ">=3.9"
  packages:
    - pandas
    - numpy
    - openpyxl
    - scipy
    - sqlparse
triggers:
  - keywords:
      - analyze data
      - profile csv
      - clean data
      - generate report
      - detect anomaly
      - nl2sql
      - data insight
      - data analysis
      - data cleaning
      - anomaly detection
      - natural language query
      - data quality report
      - data profiling
      - data report interpretation
  - file_types:
      - .csv
      - .xlsx
      - .xls
      - .json
---

# Data Insight Analyzer

## Overview

Data Insight Analyzer is an enterprise-grade structured data analysis skill that transforms raw tabular data
into actionable business intelligence. It provides five interconnected analysis pipelines covering the full
data-value lifecycle: discovery, cleansing, querying, reporting, and monitoring.

The skill is designed for production deployment with comprehensive exception handling, output sanitization,
and a layered defense strategy against malformed inputs. It supports CSV, Excel, JSON, and TSV formats
with automatic encoding detection across 9 common encodings.

## Coverage Directions

### 1. Intelligent Data Profiling
Automated statistical profiling of structured datasets. Produces summary statistics (count, mean, std, min,
quartiles, max), cardinality analysis, distribution shape indicators (skewness, kurtosis), missing-value
heatmaps, and data-type consistency checks. Identifies potential primary keys and foreign-key candidates.
Supports 15+ statistical indicators in a single pass.

### 2. Data Cleaning & Preprocessing
Rule-based and statistical data cleaning pipeline. Handles missing-value imputation (mean/median/mode/
forward-fill), outlier detection via IQR and Z-score methods, data-type coercion, whitespace normalization,
duplicate removal, and encoding repair. All cleaning operations are logged for auditability. Generates
field-level cleaning recommendations with severity ratings and alternative strategies.

### 3. NL2SQL Translation
Converts natural-language business questions into executable SQL queries. Supports Chinese and English input.
Generates dialect-aware SQL for SQLite, PostgreSQL, MySQL, and ClickHouse. Includes query validation against
the target schema, safety checks (no DROP/ALTER/TRUNCATE), and result preview. Covers SELECT, WHERE,
GROUP BY, JOIN, HAVING, and ORDER BY clauses.

### 4. Automated Report Generation & Interpretation
Produces structured Markdown reports with executive summary, key findings, statistical highlights, trend
indicators, and plain-language interpretation. Reports include data-quality scores, distribution analysis,
correlation matrices, and actionable recommendations. Every output field is sanitized against Markdown
injection and CSV formula injection.

### 5. Business Metric Anomaly Detection & Root-Cause Attribution
Multi-method anomaly detection combining statistical (IQR, Z-score, modified Z-score), temporal (rolling
mean deviation, seasonal decomposition), and ensemble approaches. Anomalies are prioritized by severity
and accompanied by differential-diagnosis-style attribution tables that rule out or confirm common root causes
(data entry error, seasonal effect, one-time event, sensor drift, processing delay, structural break).

## Standard Workflow

```
INPUT LAYER
  CSV/Excel/JSON  ->  Schema Inference  ->  Type Detection
       |
       v
VALIDATION LAYER
  Encoding check  ->  Structure validation  ->  Constraint verification
  Empty file? Malformed rows? Recursive nesting? Encoding detection
       |
       v
PROFILING LAYER
  Column-level stats  ->  Missing analysis  ->  Distribution profiling
  Outlier detection (IQR + Z-score)  ->  Correlation matrix
       |
       v
CLEANING LAYER (optional, triggered by --clean or user request)
  Missing imputation  ->  Outlier treatment  ->  Type coercion
  Duplicate removal  ->  Whitespace normalization  ->  Encoding repair
       |
       v
ANALYSIS / NL2SQL / ANOMALY LAYER
  User-selected pipeline: profiling report | NL2SQL | anomaly detection
       |
       v
OUTPUT LAYER
  Markdown report  ->  Sanitization  ->  Disclaimer  ->  Formatted tables
```

### Pipeline Selection Logic

1. If user provides a data file without explicit instructions -> run **Intelligent Data Profiling**.
2. If user mentions "clean", "cleaning", "missing", "outlier", "preprocess" -> run **Data Cleaning & Preprocessing**.
3. If user asks a natural-language question about data -> run **NL2SQL Translation**.
4. If user requests "report", "report", "summary", "interpretation" -> run **Automated Report Generation**.
5. If user mentions "anomaly", "anomaly", "spike", "drop", "attribution" -> run **Anomaly Detection & Attribution**.

## Output Specification

### Report Structure

Every final output must follow this structure:
1. Executive Summary
2. Data Quality Assessment
3. Statistical Profile (numeric + categorical)
4. Correlation Analysis (if >= 2 numeric columns)
5. Anomaly Report (if anomaly detection enabled)
6. Cleaning Audit Log (if cleaning enabled)
7. Profile Comparison (before vs after cleaning)
8. Recommendations (ranked by priority)
9. Processing Metadata
10. Disclaimer

### Field Sanitization Rules

All user-supplied string values MUST be sanitized before embedding in Markdown output. The sanitization
pipeline runs in the following strict order to prevent double-escaping:

| # | Character | Replacement | Reason |
|---|-----------|-------------|--------|
| 1 | `&` | `&amp;` | HTML entity anchor — MUST run first to avoid double-escaping |
| 2 | `<` | `&lt;` | HTML tag delimiter |
| 3 | `>` | `&gt;` | HTML tag delimiter |
| 4 | `\|` | `&#124;` | Markdown table column separator |
| 5 | `\n` / `\r` (newline) | ` ` (space) | Markdown table row breaks |
| 6 | `\t` (tab) | `    ` (4 spaces) | Field separator in table cells |
| 7 | Line starts with `=` | Prefix with `\ ` | Prevents Excel formula injection (DDE) and Setext heading |
| 8 | Line starts with `+` | Prefix with `\ ` | Prevents Excel formula injection |
| 9 | Line starts with `-` | Prefix with `\ ` | Prevents Excel formula injection and list confusion |
| 10 | Line starts with `@` | Prefix with `\ ` | Prevents mention parsing |

**Critical ordering constraint**: Step 1 (`&` -> `&amp;`) MUST execute before steps 2 and 3
(`<` -> `&lt;`, `>` -> `&gt;`), otherwise the `&` in `&lt;` would be re-escaped to `&amp;lt;`.
Similarly, step 4 (pipe) runs after HTML entities are resolved so that `&#124;` is not re-processed.
**No double-escaping**: once a character is escaped, it must not match subsequent rules.

### Numeric Precision Specification

| Context | Precision | Format |
|---------|-----------|--------|
| Count / frequency | Integer | `1234` |
| Percentage | 2 decimal places | `12.34%` |
| Mean, std, financial values | 2 decimal places | `1,234.56` |
| P-value, correlation coefficient | 4 decimal places | `0.0123` |
| Timestamp | ISO 8601 | `2025-01-15T14:30:00` |

### Severity Indicators

In executable code and scripts, use ASCII severity markers:
- `[!!]` — Critical / Error / Extreme outlier / Action required
- `[!]` — Warning / Moderate outlier / Review recommended
- `[*]` — Informational / Note / Normal observation

## Exception Input Fallback Table

The skill MUST handle the following 10 scenarios without crashing:

| # | Scenario | Detection Method | Response Strategy |
|---|----------|-----------------|-------------------|
| 1 | Empty file (0 bytes) | `os.path.getsize() == 0` | Return structured error: `{"error": "EMPTY_FILE", "message": "The input file is empty (0 bytes). Please provide a file with data.", "recoverable": false}` |
| 2 | Non-tabular content (plain text, JSON object, binary) | Attempt `pd.read_csv` / `pd.read_excel`; catch `ParserError`, `EmptyDataError`, `UnicodeDecodeError` | Return `{"error": "UNSUPPORTED_FORMAT", "message": "The file does not appear to contain tabular data. Supported formats: CSV, Excel (.xlsx/.xls), JSON array of records.", "detected_type": "<inferred_type>", "recoverable": false}` |
| 3 | Single-column CSV (no delimiter detected) | Check `len(df.columns) == 1` after parsing | Attempt secondary parsing with common delimiters (`;`, `\t`, `\|`). If still single column, return structured error with `"recoverable": true` |
| 4 | All-null columns | `df[col].isna().all()` | Flag in data-quality section with severity `[!!]`. Exclude from statistical calculations. Note: "This column contains no data and was excluded from analysis." |
| 5 | Mixed-type columns | `df[col].apply(type).nunique() > 1` | Attempt type coercion in order: numeric -> datetime -> string. Report coercion rate. Flag rows that failed coercion. |
| 6 | Encoding errors (non-UTF-8) | `UnicodeDecodeError` on read | Retry with encodings: `utf-8-sig`, `latin-1`, `gbk`, `gb2312`, `cp1252`, `shift_jis`, `utf-16`, `cp932`. Report detected encoding. |
| 7 | Extremely wide dataset (>500 columns) | `len(df.columns) > 500` | Profile only the first 100 columns for detailed statistics. Provide column-list summary for the rest. |
| 8 | Numeric overflow / extreme values | `abs(value) > 1e308` or `np.isinf(value)` | Replace with `None` for computation. Flag in anomaly report as `[!!] NUMERIC_OVERFLOW`. |
| 9 | Duplicate column names | `len(df.columns) != len(set(df.columns))` | De-duplicate by appending `_1`, `_2`, etc. Log renaming map. |
| 10 | CSV injection payloads in cells | Pattern: cell starts with `=`, `+`, `-`, `@` | Sanitize via `sanitize_md_cell()` before any output. Log a `[!]` warning per occurrence. |

## Boundaries and Security Compliance

### In-Scope
- Structured data files: CSV, TSV, Excel (.xlsx, .xls), JSON arrays of records, Parquet
- File sizes up to 500 MB (streaming parser for larger files configurable)
- Encodings: UTF-8, UTF-8-BOM, UTF-16, Latin-1, GBK, GB2312, CP1252, Shift-JIS
- Statistical analysis at the column and pairwise level
- SQL generation for SELECT queries only (read-only)

### Out-of-Scope
- Unstructured data: free text, images, audio, video, PDF documents
- Real-time streaming data sources (Kafka, WebSocket)
- Model training, machine learning inference, prediction
- Writing to production databases (SELECT-only for NL2SQL)
- Multi-file relational-join analysis (single-file focus)
- Data visualization image generation (chart images)

### Security Rules
1. **SQL Injection Prevention**: NL2SQL module generates only parameterized SELECT queries. Any attempt to
   inject DML/DDL (INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, EXEC, EXECUTE) is blocked and logged.
2. **CSV Injection Mitigation**: All string cells prefixed with `=`, `+`, `-`, `@` are escaped with a
   backslash prefix in output (see Sanitization Rules).
3. **Path Traversal Prevention**: File operations are restricted to the working directory and user-specified
   subdirectories. Any `../` sequences in paths are normalized and validated.
4. **Resource Limits**: Maximum 500 MB file size, 1000 columns, 1 million rows per analysis run.
   Configurable via environment variables `DIA_MAX_FILE_SIZE`, `DIA_MAX_COLUMNS`, `DIA_MAX_ROWS`.
5. **Sensitive Data Detection**: Columns matching patterns for credit-card numbers, SSN, email, phone,
   and API keys are flagged with `[!!]` in the data-quality report. Content is never exposed in plain text;
   only the column name and detected type are reported.
6. **No External Network Calls**: All analysis runs fully locally. No data leaves the execution environment.
7. **Deterministic Output**: Given the same input and parameters, the skill produces identical output.
8. **No Modification of Source Data**: The tool operates read-only on input files. Writes only to explicitly
   specified output paths when `--clean` or `--output` is provided.

### Privacy and Compliance
- Each output ends with the mandatory disclaimer: "The above analysis is based on the provided data; conclusions are for reference only."
- Detected PII columns (patterns: ID card, phone, email, credit card) are listed by name only; content is never exposed.
- The tool does not connect to external data sources or APIs.
- No data leaves the local execution environment.

## Resource List

| Resource | Path | Purpose |
|----------|------|---------|
| Reference Guide | `references/reference.md` | Analysis rules, anomaly thresholds, cleaning rules, NL2SQL patterns, differential diagnosis tables, encoding detection chain |
| Example Inputs | `examples/input.md` | Documented usage scenarios with real datasets (supermarket sales, data cleaning, NL2SQL, full pipeline) |
| Example Outputs | `examples/output.md` | Expected outputs for each input scenario with complete sanitized Markdown reports |
| Sample Dataset | `examples/sample_data.csv` | 36-row CSV with embedded anomalies (missing values, negative quantities, extreme outliers, invalid dates) for testing |
| Data Profiler Script | `scripts/data_profiler.py` | Python CLI tool for statistical profiling, anomaly detection, data cleaning with full sanitization pipeline |
