# Data Insight Analyzer — Reference Guide

## 1. Statistical Analysis Rules

### 1.1 Summary Statistics

For each numeric column, compute:
- **count**: Non-null observation count
- **mean**: Arithmetic mean (rounded to 2 decimal places)
- **std**: Sample standard deviation (ddof=1, rounded to 2 decimal places)
- **min**: Minimum value
- **Q1**: 25th percentile
- **median**: 50th percentile (Q2)
- **Q3**: 75th percentile
- **max**: Maximum value
- **skewness**: Fisher-Pearson coefficient (absolute value > 1 indicates substantial skew)
- **kurtosis**: Excess kurtosis (Fisher definition; > 0 = heavier tails than normal)
- **missing_pct**: Percentage of missing values (rounded to 2 decimal places)
- **unique_count**: Number of distinct values
- **cardinality_ratio**: unique_count / count (ratio > 0.9 suggests near-unique column)

For categorical/string columns, compute:
- count, unique_count, missing_pct, mode (most frequent value), mode_frequency

### 1.2 Distribution Shape Classification

| Skewness Range | Classification |
|---------------|----------------|
| \|skew\| < 0.5 | Approximately symmetric |
| 0.5 <= \|skew\| < 1.0 | Moderately skewed |
| \|skew\| >= 1.0 | Heavily skewed |

| Kurtosis Range | Classification |
|----------------|----------------|
| kurtosis < -1 | Very light tails (platykurtic) |
| -1 <= kurtosis < 0 | Light tails |
| 0 <= kurtosis < 1 | Near-normal tails |
| 1 <= kurtosis < 3 | Heavy tails (leptokurtic) |
| kurtosis >= 3 | Very heavy tails — potential outlier cluster |

### 1.3 Correlation Interpretation

| Correlation Magnitude | Interpretation |
|----------------------|----------------|
| 0.00 — 0.19 | Negligible |
| 0.20 — 0.39 | Weak |
| 0.40 — 0.59 | Moderate |
| 0.60 — 0.79 | Strong |
| 0.80 — 1.00 | Very strong |

Pearson correlation is used by default. Spearman rank correlation is used when either column has
a skewness magnitude > 2 or when > 5% of values are flagged as outliers.

## 2. Anomaly Detection Thresholds

### 2.1 IQR Method (Tukey's Fences)

- **IQR** = Q3 - Q1
- **Lower inner fence**: Q1 - 1.5 * IQR
- **Upper inner fence**: Q3 + 1.5 * IQR
- **Lower outer fence**: Q1 - 3.0 * IQR
- **Upper outer fence**: Q3 + 3.0 * IQR

Classification:
- Value outside inner fences but within outer fences → `[!] MODERATE_OUTLIER`
- Value outside outer fences → `[!!] EXTREME_OUTLIER`

### 2.2 Modified Z-Score Method

- **MAD** = median(abs(x_i - median(x)))
- **Modified Z_i** = 0.6745 * (x_i - median(x)) / MAD

Classification:
- \|Modified Z\| > 3.5 → `[!!] ANOMALY`
- 3.0 < \|Modified Z\| <= 3.5 → `[!] SUSPECT_ANOMALY`
- \|Modified Z\| <= 3.0 → Normal

The modified Z-score is preferred over standard Z-score when the data has heavy tails (kurtosis > 3).

### 2.3 Temporal Anomaly Detection (for time-series columns)

- **Rolling mean deviation**: value deviates > 3 rolling std from rolling mean (window = 7 periods)
- **Day-over-day change**: single-day change > 50% for three consecutive periods → `[!!] SUSTAINED_SHIFT`
- **Week-over-week**: same-weekday comparison; deviation > 2 std → `[!] WEEKLY_ANOMALY`

### 2.4 Ensemble Decision Rule

An observation is classified as anomalous if:
1. IQR method flags it as EXTREME_OUTLIER, OR
2. Modified Z-score flags it as ANOMALY, OR
3. Both IQR (MODERATE_OUTLIER) AND Modified Z (SUSPECT_ANOMALY) flag it

## 3. Data Cleaning Rules

### 3.1 Missing Value Strategy

| Column Type | Default Strategy | Rationale |
|-------------|-----------------|-----------|
| Numeric, skew < 0.5 | Mean imputation | Symmetric distribution — mean is representative |
| Numeric, skew >= 0.5 | Median imputation | Robust to skew |
| Numeric, missing > 30% | Column flagged, no imputation | Too sparse for reliable imputation; user must decide |
| Categorical (nominal) | Mode imputation | Most frequent category |
| Categorical (ordinal) | Median of ordinal encoding | Respects order |
| Datetime | Forward-fill then backward-fill | Temporal continuity |
| Identifier / key column | Never impute | Imputation would create invalid keys |

### 3.2 Outlier Treatment

Outliers are never automatically removed. Instead:
- Flagged in the report with severity and row index.
- If `--clean` is specified, extreme outliers are capped at outer fence bounds (Winsorization at 99th/1st percentile).
- A treatment log records every capped value with before/after.

### 3.3 Type Coercion Order

For each column, attempt coercion in this order:
1. **Numeric**: `pd.to_numeric(..., errors='coerce')` — if > 90% success, keep as numeric
2. **Datetime**: `pd.to_datetime(..., errors='coerce')` — if > 80% success and at least 5 unique values, keep as datetime
3. **String**: Fallback — strip whitespace, normalize Unicode (NFC), truncate at 10,000 chars

### 3.4 Duplicate Detection

- **Exact duplicates**: All column values identical → remove, keeping first occurrence
- **Near-duplicates**: Same primary-key candidate columns but different non-key values → flag, do not remove
- **Duplicate columns**: Correlation > 0.99 with another column → flag for review

## 4. NL2SQL Patterns

### 4.1 Supported SQL Dialects

| Dialect | LIMIT Syntax | Quote Style | String Concat | Date Function |
|---------|-------------|-------------|---------------|---------------|
| SQLite | `LIMIT N` | Double quotes | `\|\|` | `date('now')` |
| PostgreSQL | `LIMIT N` | Double quotes | `\|\|` | `CURRENT_DATE` |
| MySQL | `LIMIT N` | Backticks | `CONCAT()` | `CURDATE()` |
| ClickHouse | `LIMIT N` | Backticks | `concat()` | `today()` |

### 4.2 Query Pattern Templates

**Aggregation with filter:**
```
SELECT {group_col}, {agg_func}({value_col}) AS {alias}
FROM {table}
WHERE {condition}
GROUP BY {group_col}
ORDER BY {alias} DESC
LIMIT {n};
```

**Ranking / Top-N:**
```
SELECT * FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY {group} ORDER BY {value} DESC) AS rn
  FROM {table}
) ranked WHERE rn <= {n};
```

**Period-over-period comparison:**
```
WITH current AS (SELECT {group}, SUM({value}) AS cur_val FROM {table}
  WHERE {date_col} BETWEEN '{start}' AND '{end}' GROUP BY {group}),
prior AS (SELECT {group}, SUM({value}) AS prev_val FROM {table}
  WHERE {date_col} BETWEEN '{prior_start}' AND '{prior_end}' GROUP BY {group})
SELECT c.{group}, c.cur_val, p.prev_val,
  ROUND((c.cur_val - p.prev_val) * 100.0 / NULLIF(p.prev_val, 0), 2) AS pct_change
FROM current c LEFT JOIN prior p ON c.{group} = p.{group};
```

### 4.3 Safety Validation

Before returning a generated SQL query, validate:
1. Contains only SELECT / WITH clauses (no INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, EXEC, EXECUTE)
2. All referenced column names exist in the inferred schema
3. All referenced table names match the provided table
4. No comment-based injection (`/*`, `--` at suspicious positions)
5. `LIMIT` clause present; if absent, append `LIMIT 1000`

## 5. Output Compliance Rules

### 5.1 Report Completeness Checklist

Every output report must contain these sections:
- [ ] Executive Summary (3-5 sentence natural-language overview)
- [ ] Data Quality Assessment (missing rates, type issues, encoding, duplicate count)
- [ ] Statistical Profile (per-column summary statistics table)
- [ ] Correlation Analysis (top 5 strongest correlations for numeric columns; skip if < 2 numeric columns)
- [ ] Anomaly Report (if `--detect-anomalies` is enabled)
- [ ] Cleaning Log (if `--clean` is enabled, list every modification with row index and before/after)
- [ ] Recommendations (actionable, ranked by priority)
- [ ] Processing Metadata (file name, row count, column count, analysis duration, parameter settings)
- [ ] Disclaimer (standard legal disclaimer text)

### 5.2 Privacy and PII Handling

Columns whose names match these patterns are flagged as potentially sensitive:
- `*email*`, `*phone*`, `*ssn*`, `*credit*`, `*card*`, `*password*`, `*passwd*`, `*secret*`, `*token*`,
  `*api_key*`, `*address*`, `*name*`, `*dob*`, `*birth*`, `*id_number*`, `*身份证*`, `*手机*`, `*邮箱*`

Sensitive columns are listed by name only; their content is never included in reports.

### 5.3 Formatting Severity Indicators

In executable code and scripts, use ASCII severity markers (no emoji):

- `[!!]` — Critical / Error / Extreme outlier / Action required
- `[!]` — Warning / Moderate outlier / Review recommended
- `[*]` — Informational / Note / Normal observation

These markers map to styling in the final rendered output while keeping code emoji-free.

## 6. Differential Diagnosis Table for Data Anomalies

When an anomaly is detected, the system attempts to attribute it using the following structured
differential-diagnosis approach. Each potential cause is ruled in or out based on evidence checks.

| # | Potential Root Cause | Evidence to Rule In | Evidence to Rule Out | Confidence Rule |
|---|---------------------|--------------------|--------------------|-----------------|
| 1 | Data entry error (typo, decimal-shift) | Single-row spike, value is exactly 10x or 0.1x of neighbors, or contains non-numeric chars in numeric field | Multiple rows affected, smooth trend, value is plausible in context | If single-row AND magnitude factor of 10^n → HIGH confidence |
| 2 | Seasonal / cyclical pattern | Same period in prior cycle shows similar value, autocorrelation at lag-7 or lag-30 is high (>0.6) | No prior-cycle match, no autocorrelation structure | If autocorrelation > 0.6 at seasonal lag → HIGH confidence |
| 3 | One-time event (promotion, outage, holiday) | Anomaly cluster on same date across multiple metrics, date matches known event | Isolated to single metric, no date clustering | If multi-metric same-date → MEDIUM confidence |
| 4 | Sensor / data-feed interruption | Gap in timestamps followed by catch-up spike, or flat-line segment followed by jump | Continuous timestamps, gradual change | If timestamp-gap detected → HIGH confidence |
| 5 | Processing delay / batch upload | End-of-period spike, multiple records with identical timestamp | Evenly distributed timestamps, spike mid-period | If end-of-period cluster → MEDIUM confidence |
| 6 | Structural break (regime change) | Sustained level shift (mean before vs after differs by > 3 std), change persists for > 7 periods | Mean reverts quickly, shift is transient | If sustained > 7 periods → HIGH confidence |
| 7 | Sampling bias / population change | Anomaly coincides with change in row count or geographic distribution shift | Row count stable, distribution stable | If count-change detected → MEDIUM confidence |
| 8 | Natural variability (legitimate extreme) | All attribution checks negative, value is within physical/semantic bounds | — | If no other cause confirmed → LOW confidence (default) |

### Attribution Algorithm

```
1. For each flagged anomaly:
   a. Run all 8 evidence checks independently.
   b. Collect all causes with HIGH confidence evidence.
   c. If exactly one HIGH → attribute with HIGH confidence.
   d. If multiple HIGH → list all, rank by specificity.
   e. If zero HIGH → collect MEDIUM, rank by confidence.
   f. If zero HIGH and zero MEDIUM → attribute as "natural variability" with LOW confidence.
2. Present as an attribution table with columns:
   [Anomaly Row, Column, Value, Expected Range, Attributed Cause, Confidence]
```

## 7. Encoding Detection Chain

The skill attempts the following encodings in order when reading a CSV:

```
1. utf-8-sig   (UTF-8 with BOM — most common for Excel-exported CSV)
2. utf-8       (Standard UTF-8)
3. latin-1     (ISO-8859-1 — Western European)
4. gbk         (Chinese simplified — GBK)
5. gb2312      (Chinese simplified — older standard)
6. cp1252      (Windows Western European)
7. shift_jis   (Japanese)
8. utf-16      (UTF-16 with BOM detection)
9. cp932       (Japanese Windows)
```

Success is defined as: `pd.read_csv` completes without `UnicodeDecodeError` and produces > 0 rows.
The first successful encoding is used. The detected encoding is reported in Processing Metadata.

## 8. Resource Constraints

| Parameter | Default | Environment Variable | Description |
|-----------|---------|---------------------|-------------|
| Max file size | 500 MB | `DIA_MAX_FILE_SIZE` | Files larger than this are rejected |
| Max columns | 1000 | `DIA_MAX_COLUMNS` | Wider datasets get truncated summary |
| Max rows | 1,000,000 | `DIA_MAX_ROWS` | Larger datasets are randomly sampled |
| Max unique values for freq table | 50 | — | Columns with more unique values skip frequency table |
| Correlation matrix max columns | 50 | — | More than 50 numeric columns → show top 20 strongest |
