---
name: tool-device_info
description: "WHAT: Returns system hardware information -- CPU model and core count, total RAM, aggregate disk capacity, and the current working directory (or full GPU/partition specs when detail=true). WHEN: Use to answer 'what kind of machine am I on', to size workloads to the available RAM/CPU, or to verify disk space before large writes. WHEN NOT: Do not use for live metrics like CPU load or free RAM -- use a monitoring tool instead. Network and display details live in device_network and device_display respectively. TIPS: Start with the default summary (detail=false) for a one-line overview; set detail=true only when you need GPU names or per-partition breakdowns. PITFALLS: GPU info may be empty when no driver is exposed, and disk totals aggregate only visible partitions (network mounts are excluded)."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# device_info

WHAT: Returns system hardware information -- CPU model and core count, total RAM, aggregate disk capacity, and the current working directory (or full GPU/partition specs when detail=true). WHEN: Use to answer 'what kind of machine am I on', to size workloads to the available RAM/CPU, or to verify disk space before large writes. WHEN NOT: Do not use for live metrics like CPU load or free RAM -- use a monitoring tool instead. Network and display details live in device_network and device_display respectively. TIPS: Start with the default summary (detail=false) for a one-line overview; set detail=true only when you need GPU names or per-partition breakdowns. PITFALLS: GPU info may be empty when no driver is exposed, and disk totals aggregate only visible partitions (network mounts are excluded).
