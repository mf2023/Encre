---
name: tool-device_display
description: "WHAT: Lists all connected displays with resolution, refresh rate, DPI/scale, and primary/secondary layout information. WHEN: Use to position windows, choose screenshot regions, validate multi-monitor setups, or detect HiDPI scaling before desktop automation. WHEN NOT: For capturing pixels use the 'desktop' or 'computer_use' screenshot actions instead -- this tool returns metadata only, not images. TIPS: Pair with the 'desktop' screenshot output (which already includes DPI scale) to translate between physical and logical coordinates on HiDPI displays. PITFALLS: Disconnected or sleeping monitors may be omitted; virtual displays (RDP, headless sessions) can report zero resolution."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# device_display

WHAT: Lists all connected displays with resolution, refresh rate, DPI/scale, and primary/secondary layout information. WHEN: Use to position windows, choose screenshot regions, validate multi-monitor setups, or detect HiDPI scaling before desktop automation. WHEN NOT: For capturing pixels use the 'desktop' or 'computer_use' screenshot actions instead -- this tool returns metadata only, not images. TIPS: Pair with the 'desktop' screenshot output (which already includes DPI scale) to translate between physical and logical coordinates on HiDPI displays. PITFALLS: Disconnected or sleeping monitors may be omitted; virtual displays (RDP, headless sessions) can report zero resolution.
