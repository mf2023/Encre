---
name: tool-diagram
description: "Render text-based diagrams (Mermaid, Graphviz/DOT, or PlantUML) into PNG/SVG images, or save the DSL source for later rendering. Use this to visualize flowcharts, sequence diagrams, architecture, or UML from DSL text; pick `diagram_type` to match the source syntax. Do NOT use this for quantitative data charts (use chart), mind maps drawn freehand, or live diagram editing in a GUI. Tips: each renderer needs its CLI installed (mmdc for Mermaid, dot for Graphviz, plantuml for PlantUML); use `save_source` when a CLI is missing. Pitfalls: rendering has a 30-60s timeout and falls back to saving source on failure \u9225?verify the returned message to confirm whether an image was actually produced."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# diagram

Render text-based diagrams (Mermaid, Graphviz/DOT, or PlantUML) into PNG/SVG images, or save the DSL source for later rendering. Use this to visualize flowcharts, sequence diagrams, architecture, or UML from DSL text; pick `diagram_type` to match the source syntax. Do NOT use this for quantitative data charts (use chart), mind maps drawn freehand, or live diagram editing in a GUI. Tips: each renderer needs its CLI installed (mmdc for Mermaid, dot for Graphviz, plantuml for PlantUML); use `save_source` when a CLI is missing. Pitfalls: rendering has a 30-60s timeout and falls back to saving source on failure 鈥?verify the returned message to confirm whether an image was actually produced.
