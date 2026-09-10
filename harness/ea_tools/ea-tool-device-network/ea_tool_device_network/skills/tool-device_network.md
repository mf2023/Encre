---
name: tool-device_network
description: "WHAT: Reports live network interface information -- hostname, IPv4/IPv6 addresses, MAC addresses, link speed, and per-interface connection state. WHEN: Use when diagnosing connectivity, picking a bind address, or inventorying the host's network adapters. WHEN NOT: Not for measuring bandwidth or latency (run a speed test or ping instead) and not for managing firewall rules -- use the OS network CLI for those. TIPS: Multiple interfaces (Ethernet, Wi-Fi, virtual) are returned together; filter client-side by interface name or by the 'is_up' flag. PITFALLS: Returns 'Network information unavailable' on hosts where the provider cannot enumerate adapters; MAC addresses may be hidden on hardened systems and virtual adapters can clutter the list."
hidden: true
context: inline
tier: system-default
author: Dunimd Team
version: 0.4.3
---

# device_network

WHAT: Reports live network interface information -- hostname, IPv4/IPv6 addresses, MAC addresses, link speed, and per-interface connection state. WHEN: Use when diagnosing connectivity, picking a bind address, or inventorying the host's network adapters. WHEN NOT: Not for measuring bandwidth or latency (run a speed test or ping instead) and not for managing firewall rules -- use the OS network CLI for those. TIPS: Multiple interfaces (Ethernet, Wi-Fi, virtual) are returned together; filter client-side by interface name or by the 'is_up' flag. PITFALLS: Returns 'Network information unavailable' on hosts where the provider cannot enumerate adapters; MAC addresses may be hidden on hardened systems and virtual adapters can clutter the list.
