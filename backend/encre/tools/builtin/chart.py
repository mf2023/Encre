#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
#
# This file is part of Encre.
# The Encre project belongs to the Dunimd Team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# DISCLAIMER: Users must comply with applicable AI regulations.
# Non-compliance may result in service termination or legal liability.

from __future__ import annotations

"""Chart and visualization generator (matplotlib / plotly).

Renders line, bar, scatter, pie, histogram and heatmap charts from tabular
or list data and returns the image path plus an embedded preview.
"""

import base64
import io
import json
import os
from typing import Any

from encre.tools.base import build_tool


async def _chart_execute(**kwargs: Any) -> str:
    """Chart execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    chart_type = kwargs.get("chart_type", "line")
    title = kwargs.get("title", "")
    x_label = kwargs.get("x_label", "")
    y_label = kwargs.get("y_label", "")
    output_path = kwargs.get("output_path", "")
    width = kwargs.get("width", 10)
    height = kwargs.get("height", 6)
    dpi = kwargs.get("dpi", 100)
    fmt = kwargs.get("format", "png")
    data = kwargs.get("data", {})
    x_data = data.get("x", [])
    y_data = data.get("y", {})
    y_data_list = data.get("series", [])

    if y_data_list:
        pass
    elif y_data:
        y_data_list = [{"name": "data", "values": y_data}]
    else:
        y_data_list = []

    if not x_data and y_data_list:
        x_data = list(range(1, len(y_data_list[0].get("values", [])) + 1))

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return "Error: matplotlib is required. Install with: pip install matplotlib numpy"

    fig, ax = plt.subplots(figsize=(width, height))

    try:
        if chart_type == "line":
            for series in y_data_list:
                vals = np.array(series.get("values", []), dtype=float)
                lbl = series.get("name", "")
                marker = series.get("marker", "")
                style = series.get("style", "-")
                ax.plot(x_data[:len(vals)], vals, style, label=lbl or None, marker=marker or None)

        elif chart_type == "bar":
            x_pos = np.arange(len(x_data))
            bar_width = 0.8 / max(len(y_data_list), 1)
            for i, series in enumerate(y_data_list):
                vals = np.array(series.get("values", []), dtype=float)
                lbl = series.get("name", "")
                color = series.get("color", None)
                offset = (i - (len(y_data_list) - 1) / 2) * bar_width
                ax.bar(x_pos + offset, vals, bar_width, label=lbl or None, color=color, alpha=0.8)
            ax.set_xticks(x_pos)
            ax.set_xticklabels(x_data, rotation=45, ha="right")

        elif chart_type == "scatter":
            for series in y_data_list:
                vals = np.array(series.get("values", []), dtype=float)
                lbl = series.get("name", "")
                size = series.get("size", 20)
                ax.scatter(x_data[:len(vals)], vals, s=size, label=lbl or None, alpha=0.7)

        elif chart_type == "pie":
            labels = x_data
            values = np.array(y_data_list[0].get("values", y_data) if y_data_list else [], dtype=float)
            if len(labels) != len(values):
                return f"Error: {len(labels)} labels but {len(values)} values for pie chart."
            ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=90)
            ax.set_title(title)

        elif chart_type == "histogram":
            for series in y_data_list:
                vals = np.array(series.get("values", []), dtype=float)
                lbl = series.get("name", "")
                bins = series.get("bins", kwargs.get("bins", 20))
                ax.hist(vals, bins=bins, alpha=0.7, label=lbl or None)

        elif chart_type == "area":
            for series in y_data_list:
                vals = np.array(series.get("values", []), dtype=float)
                lbl = series.get("name", "")
                alpha = series.get("alpha", 0.3)
                ax.fill_between(range(len(vals)), vals, alpha=alpha, label=lbl or None)
            ax.set_xticks(range(len(x_data)))
            ax.set_xticklabels(x_data, rotation=45, ha="right")

        elif chart_type == "heatmap":
            matrix = data.get("matrix", y_data_list)
            if not matrix:
                return "Error: 'data.matrix' (2D list) is required for heatmap."
            arr = np.array(matrix, dtype=float)
            im = ax.imshow(arr, cmap="viridis", aspect="auto")
            plt.colorbar(im, ax=ax)
            ax.set_xticks(range(len(x_data))) if x_data and len(x_data) == arr.shape[1] else None
            ax.set_xticklabels(x_data) if x_data else None
            y_labels = data.get("y_labels", [])
            if y_labels and len(y_labels) == arr.shape[0]:
                ax.set_yticks(range(len(y_labels)))
                ax.set_yticklabels(y_labels)
            for i in range(arr.shape[0]):
                for j in range(arr.shape[1]):
                    ax.text(j, i, f"{arr[i, j]:.1f}", ha="center", va="center", color="w" if arr[i, j] > arr.max() / 2 else "k")

        else:
            plt.close(fig)
            return f"Error: Unknown chart_type '{chart_type}'. Choose: line, bar, scatter, pie, histogram, area, heatmap."

        if title:
            ax.set_title(title, fontsize=14, fontweight="bold")
        if x_label:
            ax.set_xlabel(x_label)
        if y_label:
            ax.set_ylabel(y_label)

        if chart_type not in ("pie", "heatmap"):
            ax.legend()
            ax.grid(True, alpha=0.3)

        plt.tight_layout()

        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
            fig.savefig(output_path, dpi=dpi, format=fmt)
            plt.close(fig)
            return f"Chart saved to: {os.path.abspath(output_path)}"

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi)
        plt.close(fig)
        buf.seek(0)
        encoded = base64.b64encode(buf.read()).decode("utf-8")
        return json.dumps({
            "format": "png",
            "base64": encoded,
            "description": f"{chart_type} chart{' - ' + title if title else ''}",
        })

    except Exception as e:
        plt.close(fig)
        return f"Error generating chart: {e}"


EncreChartTool = build_tool(
    name="chart",
    description=(
        "Generate data visualizations with matplotlib — line, bar, scatter, pie, "
        "histogram, area, or heatmap — and return a PNG (base64) or save to disk. "
        "Use this to render charts from in-memory tabular or list data when you need "
        "a static image for reports, slides, or quick inspection. "
        "Do NOT use this for interactive dashboards (use plotly/dash), network/graph "
        "diagrams (use diagram), or live data feeds. "
        "Tips: pass `data.x` for axis labels, `data.series` for multi-series plots "
        "(each item can carry name/values/color/marker/style/alpha/bins), and "
        "`data.matrix` with optional `data.y_labels` for heatmaps. "
        "Pitfalls: pie charts require matching label/value counts; very large "
        "datasets inflate the base64 payload — prefer `output_path` then."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "chart_type": {
                "type": "string",
                "enum": ["line", "bar", "scatter", "pie", "histogram", "area", "heatmap"],
                "description": "Visualization type to render.",
            },
            "title": {
                "type": "string",
                "description": "Title displayed at the top of the chart.",
            },
            "x_label": {
                "type": "string",
                "description": "Label for the x-axis.",
            },
            "y_label": {
                "type": "string",
                "description": "Label for the y-axis.",
            },
            "data": {
                "type": "object",
                "description": "Chart data payload. Supports data.x (list of x labels/values), data.series (list of {name, values, color?, marker?, style?, alpha?, bins?}) for multi-series charts, data.matrix (2D list) and data.y_labels for heatmaps.",
            },
            "output_path": {
                "type": "string",
                "description": "File path to save the rendered chart (e.g. 'chart.png'); when omitted, the chart is returned as a base64-encoded PNG.",
            },
            "width": {
                "type": "number",
                "description": "Figure width in inches; defaults to 10.",
            },
            "height": {
                "type": "number",
                "description": "Figure height in inches; defaults to 6.",
            },
            "format": {
                "type": "string",
                "enum": ["png", "svg", "pdf"],
                "description": "Output format when saving to output_path; defaults to png.",
            },
            "dpi": {
                "type": "integer",
                "description": "Resolution in dots per inch; defaults to 100.",
            },
            "bins": {
                "type": "integer",
                "description": "Number of bins for histogram charts; defaults to 20.",
            },
        },
        "required": ["chart_type", "data"],
    },
    execute=_chart_execute,
    intents=["data", "general", "research"],
    category="data",
    semantic_type="generate",
    is_concurrency_safe=lambda _: True,
    is_destructive=lambda args: args.get("action", "") in ("create", "save"),
)
