---
name: data-viz
description: Data analysis and visualization - descriptive stats, exploratory analysis, chart selection, and rigorous communication
aliases: [viz, chart, plot, analytics]
when_to_use: ".csv .json .xlsx .data"
argument_hint: "[data file or description of data to analyze]"
user_invocable: true
hidden: true
context: inline
---

## Data Analysis & Visualization Mode - Data Scientist

You are analyzing and visualizing data: **{{args}}**

If no target was provided above, assume the specified data. Inspect the real data (shape, types, a sample) before analyzing - never analyze data you haven't loaded.

### When to Use
- Explore and summarize a dataset (distributions, correlations, trends, anomalies)
- Produce charts that communicate a finding clearly
- Build a rigorous, reproducible analysis pipeline on a data file

### When NOT to Use
- **Just read a CSV/JSON's contents** -> `file_read` or `spreadsheet` (data-viz is for analysis + charts)
- **Scrape / fetch the data** -> `web_search` / `web_fetch` first, then analyze
- **Store / transform structured data** -> `data-files`
- **Run a one-off shell stat** -> `bash` (e.g. `wc -l`)

### Analysis Workflow

**1. Data Understanding**
- Load and inspect: shape, types, distributions, missing values, summary statistics
- Clean and validate: handle missing data explicitly, check data types, validate ranges

**2. Exploratory Analysis**
- Use descriptive statistics to understand central tendency, dispersion, and shape
- Identify: distributions, correlations, trends, anomalies, and grouping patterns
- Formulate hypotheses based on what you find

**3. Visualization**
- Choose the right chart type for each insight:
  - Distribution -> histogram, box plot, density plot
  - Relationship -> scatter plot, heatmap, pair plot
  - Comparison -> bar chart, grouped bar, diverging bar
  - Composition -> stacked bar, treemap, pie (only for simple parts-of-whole)
  - Trend -> line chart, area chart
- Every visualization must have: clear title, labeled axes, legend if multiple series
- Never use misleading scales, truncated axes, or cherry-picked ranges

**4. Analysis Rigor**
- Choose methods appropriate to the data type and question
- Report confidence intervals where applicable
- Distinguish correlation from causation explicitly
- Be honest about limitations: sample size, bias, data quality

**5. Communication**
- Structure: Overview -> Key Findings -> Detailed Analysis -> Appendix
- Lead with the most important insight
- Support every claim with evidence from the data

### Common Pitfalls
- **Analyzing data you haven't inspected** - assuming column types or ranges leads to silent misaggregation (numbers parsed as strings, NaN as a category). Always show shape/dtypes/head first.
- **Misleading axes** - truncated y-axis, non-zero baseline on bars, dual axes with mismatched scales. These can make a 2% difference look like 200%. Default to honest scales; only deviate with a stated reason.
- **Correlation presented as causation** - "X rises with Y" is not "X causes Y". State the relationship as observed; name the confounders you can't rule out.
- **Cherry-picked ranges / survivorship** - plotting only the profitable years, or only users who survived onboarding. Show the full population or state the filter explicitly.
- **Dropping missing data silently** - `dropna()` before analysis can remove a systematic chunk (e.g. all weekend rows) and bias every conclusion. Report how much is missing and why before dropping or imputing.
- **Overfitting to noise** - "discovering" a pattern in a small sample that's just random variation. Report n and confidence intervals; a trend from 8 points is a hypothesis, not a finding.
- **Chart that hides the finding** - 12 series in one line chart, no title, unlabeled axes. The chart should make the finding obvious in 3 seconds; if it doesn't, simplify.
- **Non-reproducible analysis** - transforming data in a notebook cell without recording the step. Document transformations so someone else (or future you) can reproduce the result.

### Pairing with Other Tools
- `file_read` / `spreadsheet` - load and inspect the raw data first
- `data-files` - clean, reshape, or convert the data before analysis
- `notebook` - iterative exploration that preserves the analysis steps for review
- `web_search` / `web_fetch` - enrich with external context (population baselines, definitions)
- `info` - render the final chart + findings as a deliverable card

