# Example Outputs

## Output for Scenario 1: Supermarket Sales Profiling with Anomaly Detection

```markdown
## Executive Summary

Analysis of supermarket sales data covering 36 transactions across 3 stores from 2024-07-01 to 2024-09-28.
Total net revenue: CNY 1,247,892.45. Average transaction value: CNY 34,663.68.
Data quality score: 81/100 — 7 anomalies detected, 4 missing values across 2 columns, 1 invalid date.
Two extreme outliers require immediate review (Rows 18 and 34).

## Data Quality Assessment

| Metric | Value |
|--------|-------|
| Total rows | 36 |
| Total columns | 11 |
| Complete rows (no missing values) | 32 (88.9%) |
| Rows with at least one anomaly | 6 (16.7%) |
| Duplicate rows | 0 |
| Columns with missing values | 2 (unit&#95;price, category) |
| Encoding detected | utf-8 |

### Column-Level Quality

| Column | Missing | Missing % | Data Type | Issues |
|--------|---------|-----------|-----------|--------|
| txn&#95;id | 0 | 0.00% | string | None |
| date | 0 | 0.00% | datetime | 1 invalid date (Row 23) |
| store&#95;code | 0 | 0.00% | category | None |
| category | 1 | 2.78% | category | 1 missing (Row 27) |
| product&#95;name | 0 | 0.00% | string | None |
| unit&#95;price | 1 | 2.78% | numeric | 1 missing (Row 7) |
| quantity | 0 | 0.00% | numeric | 1 negative value (Row 12) |
| discount&#95;pct | 0 | 0.00% | numeric | 1 value > 100 (Row 34) |
| gross&#95;revenue | 0 | 0.00% | numeric | 1 extreme outlier (Row 18) |
| net&#95;revenue | 1 | 2.78% | numeric | 1 missing (Row 7); 1 > gross (Row 31) |
| payment&#95;method | 0 | 0.00% | category | None |

## Statistical Profile

### Numeric Columns

| Column | Count | Mean | Std | Min | Q1 | Median | Q3 | Max | Skewness | Kurtosis | IQR |
|--------|-------|------|-----|-----|----|--------|----|-----|----------|----------|-----|
| unit&#95;price | 35 | 247.85 | 189.32 | 12.50 | 98.00 | 185.00 | 345.00 | 850.00 | 1.23 | 1.85 | 247.00 |
| quantity | 36 | 18.42 | 20.87 | -3.00 | 5.00 | 12.00 | 24.00 | 95.00 | 2.15 | 5.20 | 19.00 |
| discount&#95;pct | 36 | 14.72 | 20.45 | 0.00 | 5.00 | 10.00 | 20.00 | 150.00 | 5.01 | 35.10 | 15.00 |
| gross&#95;revenue | 36 | 42,356.78 | 32,150.44 | 850.00 | 18,200.00 | 34,500.00 | 58,900.00 | 999,999.00 | 12.35 | 180.20 | 40,700.00 |
| net&#95;revenue | 35 | 36,124.22 | 27,890.65 | 680.00 | 15,300.00 | 29,200.00 | 48,750.00 | 149,800.00 | 1.85 | 3.45 | 33,450.00 |

### Categorical Columns

| Column | Unique Count | Mode | Mode Freq | Missing % |
|--------|-------------|------|-----------|-----------|
| store&#95;code | 3 | S001 | 14 (38.9%) | 0.00% |
| category | 5 | Groceries | 10 (27.8%) | 2.78% |
| payment&#95;method | 4 | WeChat | 14 (38.9%) | 0.00% |

## Anomaly Report

### Flagged Anomalies

| Row | Column | Value | Expected Range | Method | Severity | Diagnosis |
|-----|--------|-------|---------------|--------|----------|-----------|
| 7 | unit&#95;price | (missing) | [12.50, 850.00] | Missing detection | [!!] CRITICAL | Row incomplete — missing price and revenue; possible checkout error |
| 7 | net&#95;revenue | (missing) | [680.00, 149,800.00] | Missing detection | [!!] CRITICAL | Dependent on missing unit&#95;price; cannot compute |
| 12 | quantity | -3 | [1, 95] | IQR + semantic | [!!] CRITICAL | Negative quantity — likely data entry error or return not properly recorded |
| 18 | gross&#95;revenue | 999,999.00 | [850.00, 120,050.00] | IQR outer fence | [!!] CRITICAL | 10.2x the next-highest value; likely decimal error (99,999.90 intended?) |
| 23 | date | 2024-13-45 | Valid calendar date | Date validation | [!!] CRITICAL | Month=13, Day=45 — invalid date; row excluded from time-series analysis |
| 27 | category | (missing) | {Groceries, Electronics, Apparel, Home &amp; Garden, Beverages} | Missing detection | [!] WARNING | Category unknown; assign based on product&#95;name if possible |
| 31 | net&#95;revenue | 45,200.00 | <= gross&#95;revenue (42,800.00) | Semantic check | [!] WARNING | Net revenue exceeds gross — discount may have been recorded as negative or gross is understated |
| 34 | discount&#95;pct | 150.00 | [0.00, 100.00] | Semantic bound | [!!] CRITICAL | Discount cannot exceed 100%; likely data entry error |

### Differential Diagnosis

| Anomaly | Potential Cause | Evidence | Confidence |
|---------|----------------|---------|------------|
| Row 18: gross&#95;revenue = 999,999 | Data entry error (decimal shift) | Single-row spike; value is ~10x nearest; round number pattern (999,999) | HIGH — 95% |
| Row 18: gross&#95;revenue = 999,999 | One-time bulk purchase | No other rows show similar spike; quantity is normal | RULED OUT |
| Row 12: quantity = -3 | Data entry error (sign flip) | Quantity of 3 is typical for that product | HIGH — 90% |
| Row 12: quantity = -3 | Product return | Negative quantity could indicate return; but no return flag column | LOW — 30% |
| Row 34: discount&#95;pct = 150 | Data entry error | Value exceeds semantic maximum (100%) | HIGH — 98% |
| Row 31: net > gross | Discount recorded as negative | Check if discount&#95;pct is negative (it is 0% for this row); conflicting evidence | LOW — 25% |
| Row 31: net > gross | Gross revenue understated | Gross = 42,800; net = 45,200; difference = 2,400; possible surcharge or tax recorded in net | MEDIUM — 50% |

## Correlation Analysis

Top 5 strongest pairwise correlations (numeric columns):

| Column A | Column B | Correlation | Strength |
|----------|----------|-------------|----------|
| gross&#95;revenue | net&#95;revenue | 0.987 | Very strong |
| unit&#95;price | gross&#95;revenue | 0.723 | Strong |
| quantity | gross&#95;revenue | 0.651 | Strong |
| quantity | net&#95;revenue | 0.634 | Strong |
| unit&#95;price | net&#95;revenue | 0.698 | Strong |

[*] Note: gross&#95;revenue / net&#95;revenue correlation is expected (net = gross * (1 - discount%)).
The strong correlation between unit&#95;price and revenue suggests high-value products drive total sales.

## Recommendations

1. **[!!] Investigate Row 18 (gross&#95;revenue = 999,999)** — Likely a decimal-point error. Verify against
   original POS record. If incorrect, correct to 99,999.90 before month-end close.

2. **[!!] Investigate Row 12 (quantity = -3)** — Determine if this represents a product return. If so,
   add a `transaction_type` column to distinguish sales from returns.

3. **[!!] Fix Row 34 (discount&#95;pct = 150)** — Cannot exceed 100%. Check original promotion terms.
   Likely should be 15.0% (decimal shift).

4. **[!] Review Row 31 (net > gross)** — Investigate discrepancy of CNY 2,400. May indicate an
   unrecorded surcharge, tax adjustment, or gross-revenue underreporting.

5. **[!] Address missing values** — Rows 7 and 27 have missing critical fields. Implement front-end
   validation to require unit&#95;price and category at point of sale.

6. **[*] Add data validation rules** — Prevent negative quantities, discounts outside [0,100], and
   invalid dates at data entry.

## Processing Metadata

| Field | Value |
|-------|-------|
| Input file | examples/sample&#95;data.csv |
| File size | 2,847 bytes |
| Rows processed | 36 |
| Columns processed | 11 |
| Encoding detected | utf-8 |
| Delimiter | comma (,) |
| Analysis duration | 0.84 seconds |
| Parameters | --detect-anomalies |
| Numeric columns | 5 |
| Categorical columns | 4 |
| Datetime columns | 1 |
| Identifier columns | 1 |
| Anomalies flagged | 8 |
| Missing values found | 4 |

## Disclaimer

This analysis was generated automatically by the Data Insight Analyzer. The statistical methods used
(IQR outlier detection, modified Z-score, Pearson/Spearman correlation) are standard approaches suitable
for exploratory data analysis. Results should be reviewed by a qualified analyst before making
business-critical decisions. The tool does not modify source data unless `--clean` is specified
with a different output path. No data leaves the local execution environment.
```

---

## Output for Scenario 2: Data Cleaning and Preprocessing

```markdown
## Executive Summary

Data cleaning pipeline executed on supermarket sales dataset (36 rows, 11 columns).
7 issues identified during quality assessment. All 7 issues were addressed: 2 missing values imputed,
2 outliers capped, 1 invalid date excluded, 1 semantic inconsistency corrected.
Post-cleaning data quality score: 96/100 (improved from 81/100).
Full audit log below documents every modification with before/after values.

## Pre-Cleaning Data Quality

| Metric | Value |
|--------|-------|
| Data quality score | 81 / 100 |
| Issues detected | 7 |
| Missing values | 4 (across 2 columns) |
| Anomalies | 5 |
| Invalid dates | 1 |

## Cleaning Audit Log

| Row | Column | Action | Before | After | Reason |
|-----|--------|--------|--------|-------|--------|
| 7 | unit&#95;price | Median imputation (category=Groceries) | (null) | 185.00 | Missing — imputed with category median |
| 7 | net&#95;revenue | Recalculated | (null) | 5,735.00 | Recalculated: gross&#95;revenue * (1 - discount&#95;pct/100) = 6,200 * 0.925 |
| 12 | quantity | Absolute value + flag | -3 | 3 | Negative — converted to absolute; flagged for manual review |
| 18 | gross&#95;revenue | Winsorized at outer fence | 999,999.00 | 120,050.00 | Extreme outlier — capped at Q3 + 3*IQR |
| 23 | date | Set to NaT (invalid) | 2024-13-45 | (null) | Invalid date — month=13, day=45; excluded from time-series |
| 27 | category | Mode imputation | (null) | Groceries | Missing — imputed with global mode |
| 31 | net&#95;revenue | Corrected | 45,200.00 | 42,800.00 | Net > gross — corrected to match gross (discount=0% for this row) |
| 34 | discount&#95;pct | Capped at semantic max | 150.00 | 100.00 | Value exceeds 100% — capped at maximum valid discount |

## Post-Cleaning Data Quality

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Data quality score | 81/100 | 96/100 | +15 |
| Missing values | 4 | 1 (date only) | -3 |
| Anomalies flagged | 5 | 0 | -5 |
| Complete rows | 32 (88.9%) | 35 (97.2%) | +3 |
| Rows excluded from analysis | 0 | 0 | — |

## Processing Metadata

| Field | Value |
|-------|-------|
| Input file | examples/sample&#95;data.csv |
| Cleaning mode | Enabled |
| Operations performed | 8 |
| Rows modified | 6 |
| New missing values created | 1 (date coercion) |
| Analysis duration | 1.23 seconds |

## Disclaimer

This analysis was generated automatically by the Data Insight Analyzer. Cleaning operations were
performed as specified by the `--clean` flag. All modifications are documented in the audit log above.
The original source file was not modified; cleaned data was written to the specified output path.
Results should be reviewed by a qualified analyst before loading into production systems.
No data leaves the local execution environment.
```

---

## Output for Scenario 3: NL2SQL Translation

### Query 1: "哪个门店的总净收入最高？"

**Generated SQL (SQLite dialect):**
```sql
SELECT store_code, SUM(net_revenue) AS total_net_revenue
FROM sample_data
GROUP BY store_code
ORDER BY total_net_revenue DESC
LIMIT 1;
```

**Result:**

| store&#95;code | total&#95;net&#95;revenue |
|-------------|---------------------|
| S001 | 512,340.75 |

**Interpretation**: Store S001 generated the highest total net revenue of CNY 512,340.75, representing
41.1% of total net revenue across all stores.

---

### Query 2: "电子产品类别中，折扣率超过10%的交易有多少笔？"

**Generated SQL (SQLite dialect):**
```sql
SELECT COUNT(*) AS transaction_count
FROM sample_data
WHERE category = 'Electronics' AND discount_pct > 10;
```

**Result:**

| transaction&#95;count |
|-------------------|
| 5 |

**Interpretation**: 5 transactions in the Electronics category had a discount rate exceeding 10%.
This represents 62.5% of all Electronics transactions (8 total), suggesting aggressive discounting
in this category.

---

### Query 3: "按支付方式统计，微信支付的日均净收入是多少？"

**Generated SQL (SQLite dialect):**
```sql
SELECT payment_method,
       ROUND(SUM(net_revenue) * 1.0 / COUNT(DISTINCT date), 2) AS avg_daily_net_revenue
FROM sample_data
WHERE payment_method = 'WeChat'
GROUP BY payment_method;
```

**Result:**

| payment&#95;method | avg&#95;daily&#95;net&#95;revenue |
|-----------------|--------------------------|
| WeChat | 18,456.30 |

**Interpretation**: WeChat Pay transactions generate an average of CNY 18,456.30 in net revenue per
active trading day, making it the highest-revenue payment method.

---

## Disclaimer

These SQL queries were generated automatically by the Data Insight Analyzer NL2SQL module.
All queries are read-only SELECT statements validated against the inferred schema.
Query results are based on the provided dataset snapshot. Results should be verified against
the production database for business-critical decisions.
No data leaves the local execution environment.

---

## Output for Scenario 4: Full Pipeline Report

```markdown
## Executive Summary

Full-pipeline analysis of supermarket sales data: 36 transactions, 11 columns, Q3 2024.
Pre-cleaning data quality: 81/100. Post-cleaning: 96/100.
Total net revenue: CNY 1,247,892.45. Top store: S001 (41.1% of revenue). Top category: Groceries (34.2%).
8 anomalies detected, 7 addressed via cleaning, 1 excluded (invalid date).
Two critical issues require manual investigation: Row 18 extreme revenue outlier and Row 12 negative quantity.

## Pre-Cleaning Statistical Profile

[Numeric columns table — same as Scenario 1]

## Cleaning Audit

[Full audit log — same as Scenario 2]

## Post-Cleaning Statistical Profile

### Numeric Columns (Cleaned)

| Column | Count | Mean | Std | Min | Q1 | Median | Q3 | Max | Skewness | Kurtosis | IQR |
|--------|-------|------|-----|-----|----|--------|----|-----|----------|----------|-----|
| unit&#95;price | 35 | 247.85 | 189.32 | 12.50 | 98.00 | 185.00 | 345.00 | 850.00 | 1.23 | 1.85 | 247.00 |
| quantity | 36 | 19.08 | 19.84 | 1.00 | 5.00 | 12.00 | 24.00 | 95.00 | 1.98 | 4.85 | 19.00 |
| discount&#95;pct | 36 | 12.64 | 13.82 | 0.00 | 5.00 | 10.00 | 17.50 | 100.00 | 2.85 | 12.40 | 12.50 |
| gross&#95;revenue | 36 | 38,121.45 | 25,890.33 | 850.00 | 18,200.00 | 34,500.00 | 56,400.00 | 120,050.00 | 1.45 | 2.10 | 38,200.00 |
| net&#95;revenue | 35 | 33,890.50 | 22,450.18 | 680.00 | 15,300.00 | 29,200.00 | 46,300.00 | 98,450.00 | 1.32 | 1.68 | 31,000.00 |

### Profile Comparison (Before vs After Cleaning)

| Column | Metric | Before | After | Delta |
|--------|--------|--------|-------|-------|
| quantity | Mean | 18.42 | 19.08 | +0.66 |
| discount&#95;pct | Mean | 14.72 | 12.64 | -2.08 |
| discount&#95;pct | Std | 20.45 | 13.82 | -6.63 |
| gross&#95;revenue | Mean | 42,356.78 | 38,121.45 | -4,235.33 |
| gross&#95;revenue | Std | 32,150.44 | 25,890.33 | -6,260.11 |
| gross&#95;revenue | Max | 999,999.00 | 120,050.00 | -879,949.00 |

## Anomaly Detection (Post-Cleaning)

After cleaning, 0 anomalies remain above threshold. The original 8 anomalies were resolved as follows:
- 2 missing values: imputed
- 3 semantic violations: corrected
- 2 extreme outliers: capped (Winsorized)
- 1 invalid date: excluded

## Key Business Findings

1. **Revenue Concentration**: Store S001 generates 41.1% of total net revenue. S003 underperforms at 24.5%.
   Consider store-level performance review.

2. **Payment Mix**: WeChat Pay dominates (38.9% of transactions), followed by Alipay (30.6%), Cash (19.4%),
   and Card (11.1%). Digital payments together represent 69.5% of transactions.

3. **Category Performance**: Groceries lead at 34.2% of revenue with the lowest average discount (6.2%).
   Electronics have the highest discount rate (avg 18.5%), suggesting margin pressure.

4. **Discount Effectiveness**: Transactions with discounts > 20% generate 23% higher quantities but only
   8% higher net revenue, indicating discount dilution.

## Recommendations

1. **[!!] Investigate Store S003 underperformance** — Revenue 40% below S001. Check foot traffic,
   inventory levels, and staffing.

2. **[!] Review Electronics pricing strategy** — High discount rate (18.5% avg) with modest volume
   uplift suggests price sensitivity or competitive pressure.

3. **[!] Implement POS validation rules** — Prevent negative quantities, invalid dates, impossible
   discounts at point of entry. Estimated cost: 2-3 engineering days. ROI: eliminates 100% of
   systematic data errors at source.

4. **[*] Optimize discount tiers** — Analyze the relationship between discount depth and quantity
   uplift to find the optimal discount level per category. Current data suggests diminishing
   returns beyond 20% discount.

5. **[*] Add transaction-type column** — Distinguish sales, returns, exchanges, and voided
   transactions for cleaner analysis.

## Processing Metadata

| Field | Value |
|-------|-------|
| Input file | examples/sample&#95;data.csv |
| File size | 2,847 bytes |
| Rows processed | 36 |
| Columns processed | 11 |
| Pipeline stages | profile, clean, anomaly-detect |
| Cleaning operations | 8 |
| Anomalies detected | 8 (pre-clean), 0 (post-clean) |
| Analysis duration | 2.05 seconds |
| Encoding | utf-8 |

## Disclaimer

This analysis was generated automatically by the Data Insight Analyzer using statistical methods
(IQR, modified Z-score, Pearson/Spearman correlation). All cleaning operations are documented in
the audit log. The original source file was not modified. Results and recommendations are
exploratory in nature and should be reviewed by a qualified business analyst before making
operational or strategic decisions. No data leaves the local execution environment.
```
