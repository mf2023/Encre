---
name: tool-chart
description: "Generate data visualizations with matplotlib \u9225?line, bar, scatter, pie, histogram, area, or heatmap \u9225?and return a PNG (base64) or save to disk. Use this to render charts from in-memory tabular or list data when you need a static image for reports, slides, or quick inspection. Do NOT use this for interactive dashboards (use plotly/dash), network/graph diagrams (use diagram), or live data feeds. Tips: pass `data.x` for axis labels, `data.series` for multi-series plots (each item can carry name/values/color/marker/style/alpha/bins), and `data.matrix` with optional `data.y_labels` for heatmaps. Pitfalls: pie charts require matching label/value counts; very large datasets inflate the base64 payload \u9225?prefer `output_path` then."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# chart

Generate data visualizations with matplotlib 鈥?line, bar, scatter, pie, histogram, area, or heatmap 鈥?and return a PNG (base64) or save to disk. Use this to render charts from in-memory tabular or list data when you need a static image for reports, slides, or quick inspection. Do NOT use this for interactive dashboards (use plotly/dash), network/graph diagrams (use diagram), or live data feeds. Tips: pass `data.x` for axis labels, `data.series` for multi-series plots (each item can carry name/values/color/marker/style/alpha/bins), and `data.matrix` with optional `data.y_labels` for heatmaps. Pitfalls: pie charts require matching label/value counts; very large datasets inflate the base64 payload 鈥?prefer `output_path` then.
