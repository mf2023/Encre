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

"""Diagram rendering tool (Mermaid / Graphviz / PlantUML).

Converts textual diagram DSLs into rendered images (flowcharts, sequence
diagrams, UML, etc.) and returns the image path plus diagnostics.
"""


import asyncio
import contextlib
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from encre.tools.base import build_tool


async def _diagram_execute(**kwargs: Any) -> str:
    """Diagram execute.

    Args:
        kwargs: Description of the kwargs parameter.
    """
    action = kwargs.get("action", "")
    diagram_type = kwargs.get("diagram_type", "mermaid")
    source = kwargs.get("source", "")
    output_path = kwargs.get("output_path", "")
    width = kwargs.get("width", 0)
    theme = kwargs.get("theme", "default")

    if action == "generate":
        if not source:
            return "Missing required field: source"

        if diagram_type == "mermaid":
            return await _handle_mermaid(source, output_path, theme, width)
        elif diagram_type == "graphviz":
            return await _handle_graphviz(source, output_path, "png")
        elif diagram_type == "plantuml":
            return await _handle_plantuml(source, output_path)
        else:
            return f"Unsupported diagram type: {diagram_type}. Supported: mermaid, graphviz, plantuml"

    elif action == "save_source":
        if not source or not output_path:
            return "Missing required fields: source, output_path"
        try:
            p = Path(output_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(source, encoding="utf-8")
            return f"Diagram source saved to {output_path}"
        except Exception as e:
            return f"Failed to save diagram source: {e}"

    return f"Unknown action: {action}. Supported: generate, save_source"


async def _handle_mermaid(source: str, output_path: str, theme: str, width: int) -> str:
    """Handle mermaid.

    Args:
        source: Description of the source parameter.
        output_path: Description of the output_path parameter.
        theme: Description of the theme parameter.
        width: Description of the width parameter.
    """
    diagram_path = ""
    tmp_dir = None
    try:
        tmp_dir_obj = tempfile.TemporaryDirectory(prefix="encre_mermaid_")
        tmp_dir = tmp_dir_obj.name
        mmd_path = os.path.join(tmp_dir, "diagram.mmd")
        Path(mmd_path).write_text(source, encoding="utf-8")

        diagram_path = output_path or os.path.join(tmp_dir, "diagram.png")

        Path(diagram_path).parent.mkdir(parents=True, exist_ok=True)

        cmd = ["mmdc", "-i", mmd_path, "-o", diagram_path]
        if theme != "default":
            cmd.extend(["-t", theme])
        if width > 0:
            cmd.extend(["-w", str(width)])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

        if proc.returncode == 0:
            return f"Mermaid diagram rendered to {diagram_path}"
        else:
            fallback = f"mmdc CLI not available or failed. Source saved to {mmd_path}.\nSTDERR: {stderr.decode()[:1000]}"
            return fallback

    except FileNotFoundError:
        src_path = output_path or os.path.join(os.getcwd(), "diagram.mmd")
        Path(src_path).parent.mkdir(parents=True, exist_ok=True)
        Path(src_path).write_text(source, encoding="utf-8")
        return f"Mermaid source saved to {src_path}. Install mermaid-cli (npm i -g @mermaid-js/mermaid-cli) for rendering."
    except subprocess.TimeoutExpired:
        return "Mermaid rendering timed out (60s). Source was saved."
    except Exception as e:
                    return f"Failed to render Mermaid diagram: {e}"
    finally:
        if tmp_dir_obj:
            with contextlib.suppress(Exception):
                tmp_dir_obj.cleanup()


async def _handle_graphviz(source: str, output_path: str, output_format: str) -> str:
    """Handle graphviz.

    Args:
        source: Description of the source parameter.
        output_path: Description of the output_path parameter.
        output_format: Description of the output_format parameter.
    """
    try:
        if not output_path:
            output_path = os.path.join(os.getcwd(), "diagram.png")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            "dot", "-T" + output_format, "-o", output_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=source.encode("utf-8")), timeout=30
        )

        if proc.returncode == 0:
            return f"Graphviz diagram rendered to {output_path}"
        return f"Graphviz rendering failed: {stderr.decode()[:1000]}"
    except FileNotFoundError:
        return "Graphviz (dot) not found. Install graphviz (apt install graphviz or brew install graphviz)."
    except subprocess.TimeoutExpired:
        return "Graphviz rendering timed out."
    except Exception as e:
        return f"Failed to render Graphviz diagram: {e}"


async def _handle_plantuml(source: str, output_path: str) -> str:
    """Handle plantuml.

    Args:
        source: Description of the source parameter.
        output_path: Description of the output_path parameter.
    """
    try:
        if not output_path:
            output_path = os.path.join(os.getcwd(), "diagram.png")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        tmp_file = os.path.join(tempfile.gettempdir(), "encre_plantuml.puml")
        Path(tmp_file).write_text(source, encoding="utf-8")

        proc = await asyncio.create_subprocess_exec(
            "plantuml", "-tpng", tmp_file, "-o", str(Path(output_path).parent),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        if Path(output_path).exists():
            return f"PlantUML diagram rendered to {output_path}"
        return f"PlantUML rendering failed: {stderr.decode()[:1000]}"
    except FileNotFoundError:
        return "PlantUML not found. Install from https://plantuml.com or use 'save_source' action."
    except subprocess.TimeoutExpired:
        return "PlantUML rendering timed out."
    except Exception as e:
        return f"Failed to render PlantUML diagram: {e}"
    finally:
        with contextlib.suppress(Exception):
            Path(tmp_file).unlink(missing_ok=True)


EncreDiagramTool = build_tool(
    name="diagram",
    description="Generate diagrams from text. Supports Mermaid, Graphviz (DOT), PlantUML. Render to PNG/SVG via CLI tools or save source.",
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["generate", "save_source"],
                "description": "Action to perform",
            },
            "diagram_type": {
                "type": "string",
                "enum": ["mermaid", "graphviz", "plantuml"],
                "description": "Diagram language/type",
            },
            "source": {"type": "string", "description": "Diagram source code (Mermaid, DOT, or PlantUML syntax)"},
            "output_path": {"type": "string", "description": "Output file path for rendered image or source file"},
            "width": {"type": "integer", "description": "Output image width in pixels (Mermaid only)"},
            "theme": {
                "type": "string",
                "enum": ["default", "dark", "neutral", "forest", "base"],
                "description": "Mermaid theme (default: default)",
            },
        },
        "required": ["action"],
    },
    execute=_diagram_execute,
    intents=["general", "coding", "data"],
    category="docs",
    semantic_type="generate",
    cost_level="low",
    retryability="auto",
    is_concurrency_safe=lambda _: True,
    is_destructive=lambda args: args.get("action", "") in ("generate", "save_source"),
)
