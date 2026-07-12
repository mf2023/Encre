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
    description="""Generate data visualizations and charts using matplotlib.

Supports: line, bar, scatter, pie, histogram, area, and heatmap charts.
Returns the chart as a PNG base64-encoded image or saves to a file.

Data format:
- data.x: list of x-axis labels/values
- data.y: dict of {name: [values]} for single series
- data.series: list of {name, values, color, marker, style, alpha, bins} for multi-series
- data.matrix: 2D list for heatmap
- data.y_labels: y-axis labels for heatmap

Example:
  chart_type="line", title="Sales Trend",
  x_label="Month", data={x: ["Jan","Feb","Mar"], series: [{name: "Sales", values: [100,150,130]}]}""",
    input_schema={
        "type": "object",
        "properties": {
            "chart_type": {
                "type": "string",
                "enum": ["line", "bar", "scatter", "pie", "histogram", "area", "heatmap"],
                "description": "Type of chart to generate",
            },
            "title": {
                "type": "string",
                "description": "Chart title",
            },
            "x_label": {
                "type": "string",
                "description": "X-axis label",
            },
            "y_label": {
                "type": "string",
                "description": "Y-axis label",
            },
            "data": {
                "type": "object",
                "description": "Chart data: {x: [...], series: [{name, values, color?, marker?, style?}]}",
            },
            "output_path": {
                "type": "string",
                "description": "File path to save the chart (e.g. chart.png). If empty, returns base64.",
            },
            "width": {
                "type": "number",
                "description": "Figure width in inches (default: 10)",
            },
            "height": {
                "type": "number",
                "description": "Figure height in inches (default: 6)",
            },
            "format": {
                "type": "string",
                "enum": ["png", "svg", "pdf"],
                "description": "Output format (default: png)",
            },
            "dpi": {
                "type": "integer",
                "description": "Image DPI (default: 100)",
            },
            "bins": {
                "type": "integer",
                "description": "Number of bins for histogram (default: 20)",
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
