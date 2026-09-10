---
name: tool-device_battery
description: "WHAT: Returns the current battery state -- charge percentage, whether AC power is plugged in, and estimated seconds remaining (when the OS provides it). WHEN: Use to decide whether to defer expensive work, gate long-running tasks, or warn the user before a critical shutdown. WHEN NOT: Not for measuring power consumption over time -- use a profiling tool. On desktops without a UPS the call returns 'No battery detected'. TIPS: Poll periodically rather than in a tight loop; battery state changes slowly and frequent reads add no value. PITFALLS: 'seconds remaining' is an estimate and can jump when the load changes; treat it as advisory, not exact."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# device_battery

WHAT: Returns the current battery state -- charge percentage, whether AC power is plugged in, and estimated seconds remaining (when the OS provides it). WHEN: Use to decide whether to defer expensive work, gate long-running tasks, or warn the user before a critical shutdown. WHEN NOT: Not for measuring power consumption over time -- use a profiling tool. On desktops without a UPS the call returns 'No battery detected'. TIPS: Poll periodically rather than in a tight loop; battery state changes slowly and frequent reads add no value. PITFALLS: 'seconds remaining' is an estimate and can jump when the load changes; treat it as advisory, not exact.
